"""Simulated listeners for the demo.

Target plus Gaussian noise, with front/back reversals at a known rate per
condition, so the analysis should find about 0.10 (itd_ild) and 0.50 (ild_only).
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from binaural_loc.config import load_config
from binaural_loc.experiment import find_trial_list
from binaural_loc.server.app import create_app

FRONT_BACK_RATE = {"itd_ild": 0.10, "ild_only": 0.50}
AZIMUTH_SD, ELEVATION_SD = 8.0, 10.0
SESSION = "SIM"


def simulate(config_path: Path, participants: list[str], seed: int = 0) -> None:
    cfg = load_config(config_path)
    with open(cfg.manifest, newline="") as f:
        manifest = {r["stimulus_id"]: r for r in csv.DictReader(f)}
    client = TestClient(create_app(cfg, serve_web=False))
    rng = np.random.default_rng(seed)
    labels = len(cfg.response.externalization_labels)

    for pid in participants:
        ids = {"participant_id": pid, "session_id": SESSION}
        session = client.post("/api/session", json=ids).json()
        with open(find_trial_list(cfg.trial_lists, pid, SESSION), newline="") as f:
            stim_by_index = {int(r["trial_index"]): r["stimulus_id"] for r in csv.DictReader(f)}
        done = set(session["completed"])
        for t in session["trials"]:
            if t["trial_index"] in done:
                continue
            m = manifest[stim_by_index[t["trial_index"]]]
            az, el = float(m["target_azimuth"]), float(m["target_elevation"])
            if rng.random() < FRONT_BACK_RATE.get(m.get("condition", ""), 0.0):
                az = 180.0 - az
            now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            body = {
                **ids,
                "response_azimuth": float((az + rng.normal(0, AZIMUTH_SD)) % 360),
                "response_elevation": float(np.clip(el + rng.normal(0, ELEVATION_SD), -90, 90))
                if cfg.response.mode == "azimuth_elevation" else None,
                "response_externalization": int(rng.integers(1, labels + 1))
                if cfg.response.externalization == "rating" else None,
                "rt_ms": float(rng.uniform(1500, 4000)),
                "n_replays": 0,
                "n_azimuth_clicks": 1,
                "n_elevation_clicks": 1,
                "client_trial_started_at": now,
                "client_confirmed_at": now,
                "audio_sample_rate": float(cfg.sample_rate),
            }
            r = client.post(f"/api/trials/{t['trial_index']}/response", json=body)
            r.raise_for_status()
    print(f"simulated {len(participants)} listener(s), session {SESSION}")
