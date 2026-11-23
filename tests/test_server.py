from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from binaural_loc.config import load_config
from binaural_loc.server.app import create_app
from binaural_loc.server.results import JsonlLog

IDS = {"participant_id": "P01", "session_id": "S1"}


def answer(**over):
    body = {
        **IDS,
        "response_azimuth": 80.5,
        "response_elevation": 10.0,
        "response_externalization": None,
        "rt_ms": 1234.0,
        "n_replays": 0,
        "n_azimuth_clicks": 1,
        "n_elevation_clicks": 2,
        "client_trial_started_at": "2026-10-07T10:00:00.000Z",
        "client_confirmed_at": "2026-10-07T10:00:02.000Z",
        "audio_sample_rate": 48000,
    }
    body.update(over)
    return body


@pytest.fixture
def client(experiment: Path) -> TestClient:
    return TestClient(create_app(load_config(experiment), serve_web=False))


def results_file(experiment: Path) -> Path:
    return experiment.parent / "results" / "P01_S1.jsonl"


def test_session_exposes_only_opaque_names(client: TestClient):
    r = client.post("/api/session", json=IDS)
    assert r.status_code == 200
    body = r.json()
    assert [t["trial_index"] for t in body["trials"]] == [0, 1, 2, 3]
    assert body["completed"] == []
    text = json.dumps(body)
    for leak in ("measured", "uniform", "random", "pca", "is_catch", "target", "stimulus_id", ".csv"):
        assert leak not in text
    # repeated stimulus -> same opaque file, so it is decoded once
    assert body["trials"][0]["audio"] == body["trials"][3]["audio"]


def test_audio_served_without_real_filename(client: TestClient):
    body = client.post("/api/session", json=IDS).json()
    r = client.get(body["trials"][1]["audio"])
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert "content-disposition" not in r.headers
    assert client.get("/api/audio/s_000000000000.wav").status_code == 404
    assert client.get(body["volume_reference"]).status_code == 200


def test_training_feedback_and_main_no_feedback(client: TestClient, experiment: Path):
    client.post("/api/session", json=IDS)
    r = client.post("/api/trials/0/response", json=answer())
    assert r.json() == {"status": "saved", "feedback": {"azimuth": 0.0, "elevation": 0.0}}
    r = client.post("/api/trials/1/response", json=answer())
    assert r.json() == {"status": "saved", "feedback": None}

    rows = [json.loads(line) for line in results_file(experiment).read_text().splitlines()]
    assert [r["trial_index"] for r in rows] == [0, 1]
    assert rows[1]["stimulus_id"] == "uniform_pca_az90"  # server side only
    assert rows[1]["response_method"] == "gui_top_side_v1"
    assert rows[1]["response_azimuth"] == 80.5 and rows[1]["n_elevation_clicks"] == 2


def test_duplicate_response_written_once(client: TestClient, experiment: Path):
    client.post("/api/session", json=IDS)
    assert client.post("/api/trials/2/response", json=answer()).json()["status"] == "saved"
    assert client.post("/api/trials/2/response", json=answer(response_azimuth=1)).json()["status"] == "duplicate"
    rows = results_file(experiment).read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["is_catch"] is True


def test_resume_after_server_restart(experiment: Path):
    c1 = TestClient(create_app(load_config(experiment), serve_web=False))
    c1.post("/api/session", json=IDS)
    c1.post("/api/trials/0/response", json=answer())
    c1.post("/api/trials/1/response", json=answer())
    # fresh app = server restarted; the browser may still be open and keep posting
    c2 = TestClient(create_app(load_config(experiment), serve_web=False))
    assert c2.post("/api/trials/2/response", json=answer()).json()["status"] == "saved"
    assert c2.post("/api/session", json=IDS).json()["completed"] == [0, 1, 2]


@pytest.mark.parametrize(
    "over, code",
    [
        ({"response_elevation": None}, 422),
        ({"n_replays": 2}, 422),  # max_replays is 1
        ({"response_azimuth": 360}, 422),
        ({"response_elevation": 91}, 422),
        ({"participant_id": "../etc"}, 400),
        ({"participant_id": "P99"}, 404),
    ],
)
def test_response_validation(client: TestClient, over: dict, code: int):
    assert client.post("/api/trials/1/response", json=answer(**over)).status_code == code


def test_unknown_trial(client: TestClient):
    assert client.post("/api/trials/99/response", json=answer()).status_code == 404


def test_externalization_rating_required_when_enabled(experiment: Path):
    experiment.write_text(experiment.read_text().replace("externalization: off", "externalization: rating"))
    c = TestClient(create_app(load_config(experiment), serve_web=False))
    assert c.post("/api/trials/1/response", json=answer()).status_code == 422
    assert c.post("/api/trials/1/response", json=answer(response_externalization=5)).status_code == 422
    assert c.post("/api/trials/1/response", json=answer(response_externalization=4)).status_code == 200


def test_azimuth_only_stores_no_elevation(experiment: Path):
    experiment.write_text(experiment.read_text().replace("mode: azimuth_elevation", "mode: azimuth_only"))
    c = TestClient(create_app(load_config(experiment), serve_web=False))
    assert c.post("/api/trials/1/response", json=answer(response_elevation=None)).status_code == 200
    assert json.loads(results_file(experiment).read_text())["response_elevation"] is None


def test_events_logged(client: TestClient, experiment: Path):
    client.post("/api/session", json=IDS)
    client.post("/api/event", json={**IDS, "event": "lr_check_confirmed", "data": {"audio_sample_rate": 48000}})
    events = [json.loads(line) for line in (experiment.parent / "results" / "P01_S1.events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["session_opened", "lr_check_confirmed"]


def test_jsonl_recovers_from_torn_write(tmp_path: Path):
    p = tmp_path / "r.jsonl"
    p.write_text('{"trial_index": 0}\n{"trial_ind')  # crash mid-line
    log = JsonlLog(p)
    log.append({"trial_index": 1})
    assert [r["trial_index"] for r in log.read()] == [0, 1]
