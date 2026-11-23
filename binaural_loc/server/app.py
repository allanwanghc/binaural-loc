from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..config import Config
from ..experiment import (
    ExperimentError,
    Stimulus,
    Trial,
    audio_token,
    check_id,
    find_trial_list,
    load_manifest,
    load_trial_list,
)
from .results import JsonlLog, results_paths

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
RESPONSE_METHOD = "gui_top_side_v1"
VOLUME_REFERENCE_KEY = "__volume_reference__"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Session:
    participant_id: str
    session_id: str
    trial_list: Path
    trials: dict[int, Trial]
    results: JsonlLog
    events: JsonlLog
    completed: set[int] = field(default_factory=set)


class SessionRequest(BaseModel):
    participant_id: str
    session_id: str


class ResponseRequest(BaseModel):
    participant_id: str
    session_id: str
    response_azimuth: float = Field(ge=0, lt=360)
    response_elevation: float | None = Field(default=None, ge=-90, le=90)
    response_externalization: int | None = None
    rt_ms: float = Field(ge=0)
    n_replays: int = Field(ge=0)
    n_azimuth_clicks: int = Field(ge=0)
    n_elevation_clicks: int = Field(ge=0)
    client_trial_started_at: str
    client_confirmed_at: str
    audio_sample_rate: float


class EventRequest(BaseModel):
    participant_id: str
    session_id: str
    event: str = Field(max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


def create_app(config: Config, stimuli: dict[str, Stimulus] | None = None, serve_web: bool = True) -> FastAPI:
    stimuli = stimuli if stimuli is not None else load_manifest(config.manifest, config.sample_rate)
    sessions: dict[tuple[str, str], Session] = {}
    audio_files: dict[str, Path] = {}  # opaque token -> wav path
    lock = threading.Lock()

    app = FastAPI(title="binaural-loc", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    def get_session(pid: str, sid: str) -> Session:
        # also re-opens a session if the server was restarted under an open page
        try:
            check_id(pid, "participant ID")
            check_id(sid, "session ID")
        except ExperimentError as e:
            raise HTTPException(400, str(e)) from None
        with lock:
            s = sessions.get((pid, sid))
            if s is not None:
                return s
            try:
                path = find_trial_list(config.trial_lists, pid, sid)
                trials = load_trial_list(path, stimuli, participant_id=pid)
            except ExperimentError as e:
                raise HTTPException(404, str(e)) from None
            res_path, ev_path = results_paths(config.results, pid, sid)
            s = Session(pid, sid, path, {t.trial_index: t for t in trials}, JsonlLog(res_path), JsonlLog(ev_path))
            s.completed = {int(r["trial_index"]) for r in s.results.read() if "trial_index" in r}
            for t in trials:
                audio_files[audio_token(pid, sid, t.stimulus_id)] = stimuli[t.stimulus_id].path
            if config.volume_reference is not None:
                audio_files[audio_token(pid, sid, VOLUME_REFERENCE_KEY)] = config.volume_reference
            sessions[(pid, sid)] = s
            return s

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return config.public()

    @app.post("/api/session")
    def open_session(req: SessionRequest) -> dict[str, Any]:
        s = get_session(req.participant_id, req.session_id)
        ordered = sorted(s.trials.values(), key=lambda t: t.trial_index)
        s.events.append({
            "event": "session_opened",
            "server_time": now_iso(),
            "trial_list": s.trial_list.name,
            "n_trials": len(ordered),
            "n_completed": len(s.completed),
            "software_version": __version__,
        })
        if config.volume_reference is not None:
            ref = audio_token(s.participant_id, s.session_id, VOLUME_REFERENCE_KEY)
        else:
            ref = audio_token(s.participant_id, s.session_id, ordered[0].stimulus_id)
        return {
            "trials": [
                {
                    "trial_index": t.trial_index,
                    "block": t.block,
                    "is_training": t.is_training,
                    "audio": f"/api/audio/{audio_token(s.participant_id, s.session_id, t.stimulus_id)}.wav",
                }
                for t in ordered
            ],
            "completed": sorted(s.completed),
            "volume_reference": f"/api/audio/{ref}.wav",
        }

    @app.get("/api/audio/{name}")
    def get_audio(name: str) -> FileResponse:
        token = name.removesuffix(".wav")
        path = audio_files.get(token)
        if path is None:
            raise HTTPException(404, "unknown audio")
        # no `filename`: it would reveal the real name in Content-Disposition
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.post("/api/trials/{trial_index}/response")
    def save_response(trial_index: int, req: ResponseRequest) -> dict[str, Any]:
        s = get_session(req.participant_id, req.session_id)
        trial = s.trials.get(trial_index)
        if trial is None:
            raise HTTPException(404, f"trial {trial_index} not in this participant's list")
        mode = config.response.mode
        if mode == "azimuth_elevation" and req.response_elevation is None:
            raise HTTPException(422, "response_elevation required in azimuth_elevation mode")
        n_labels = len(config.response.externalization_labels)
        if config.response.externalization == "rating":
            if req.response_externalization is None or not 1 <= req.response_externalization <= n_labels:
                raise HTTPException(422, f"response_externalization must be 1..{n_labels}")
        if req.n_replays > config.max_replays:
            raise HTTPException(422, "more replays than max_replays")

        stim = stimuli[trial.stimulus_id]
        feedback = (
            {"azimuth": stim.target_azimuth, "elevation": stim.target_elevation} if trial.is_training else None
        )
        with lock:
            if trial_index in s.completed:  # retried request
                return {"status": "duplicate", "feedback": feedback}
            s.results.append({
                "participant_id": s.participant_id,
                "session_id": s.session_id,
                "trial_index": trial.trial_index,
                "block": trial.block,
                "stimulus_id": trial.stimulus_id,
                "is_training": trial.is_training,
                "is_catch": trial.is_catch,
                "list_seed": trial.list_seed,
                "response_method": RESPONSE_METHOD,
                "response_mode": mode,
                "response_azimuth": req.response_azimuth,
                "response_elevation": req.response_elevation if mode == "azimuth_elevation" else None,
                "response_externalization": req.response_externalization,
                "rt_ms": req.rt_ms,
                "n_replays": req.n_replays,
                "n_azimuth_clicks": req.n_azimuth_clicks,
                "n_elevation_clicks": req.n_elevation_clicks,
                "client_trial_started_at": req.client_trial_started_at,
                "client_confirmed_at": req.client_confirmed_at,
                "server_saved_at": now_iso(),
                "audio_sample_rate": req.audio_sample_rate,
                "trial_list": s.trial_list.name,
                "software_version": __version__,
            })
            s.completed.add(trial_index)
        return {"status": "saved", "feedback": feedback}

    @app.post("/api/event")
    def log_event(req: EventRequest) -> dict[str, str]:
        s = get_session(req.participant_id, req.session_id)
        s.events.append({"event": req.event, "server_time": now_iso(), **req.data})
        return {"status": "ok"}

    if serve_web and WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app
