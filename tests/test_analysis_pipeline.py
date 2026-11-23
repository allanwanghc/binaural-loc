from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from binaural_loc.analysis import merge, summarize
from binaural_loc.cli import main
from binaural_loc.config import load_config
from binaural_loc.server.app import create_app

from .test_server import IDS, answer


@pytest.fixture
def results(experiment: Path) -> Path:
    c = TestClient(create_app(load_config(experiment), serve_web=False))
    c.post("/api/session", json=IDS)
    # trial 0 training (measured, target 0/0), 1: uniform_pca 90/30, 2: catch, 3: measured 0/0
    c.post("/api/trials/0/response", json=answer(response_azimuth=10, response_elevation=0))
    c.post("/api/trials/1/response", json=answer(response_azimuth=90, response_elevation=10))
    c.post("/api/trials/2/response", json=answer(response_azimuth=225, response_elevation=-20))
    c.post("/api/trials/3/response", json=answer(response_azimuth=180, response_elevation=0))
    return experiment


def test_merge_joins_manifest_and_filters(results: Path):
    base = results.parent
    df = merge(base / "results", base / "stimuli" / "manifest.csv")
    assert list(df["trial_index"]) == [1, 3]  # training and catch excluded by default
    assert list(df["reconstruction"]) == ["uniform_pca", "measured"]  # manifest metadata passed through
    row1, row3 = df.iloc[0], df.iloc[1]
    assert row1["elevation_error"] == pytest.approx(-20)
    assert row1["azimuth_error"] == pytest.approx(0)
    assert row3["front_back_confusion"] == 1 and row3["quadrant_error"] == 1
    assert row3["great_circle_error_fb_resolved"] == pytest.approx(0, abs=1e-6)

    all_ = merge(base / "results", base / "stimuli" / "manifest.csv", include_training=True, include_catch=True)
    assert list(all_["trial_index"]) == [0, 1, 2, 3]
    assert "file_path" in all_.columns and "stim_trial_index" not in all_.columns


def test_summary_by_condition(results: Path):
    base = results.parent
    df = merge(base / "results", base / "stimuli" / "manifest.csv")
    s = summarize(df, by=["participant_id", "reconstruction"])
    q = s[(s.metric == "quadrant_error")].set_index("reconstruction")
    assert q.loc["measured", "mean"] == 1 and q.loc["measured", "n"] == 1
    # target az 90 / el 30 has lateral angle 60 > 30: outside the polar-analysis range
    assert q.loc["uniform_pca", "n"] == 0
    lat = s[(s.metric == "lateral_error")].set_index("reconstruction")
    assert lat.loc["uniform_pca", "n"] == 1


def test_cli_analyze_writes_csvs(results: Path, capsys):
    main(["analyze", "--config", str(results), "--by", "participant_id,reconstruction"])
    out = results.parent / "results" / "analysis"
    trials = pd.read_csv(out / "trials.csv")
    summary = pd.read_csv(out / "summary.csv")
    assert len(trials) == 2
    assert {"participant_id", "reconstruction", "metric", "n", "mean", "median", "rms", "sd"} <= set(summary.columns)
    # the analysis folder's own files are not picked up as results on a second run
    main(["analyze", "--config", str(results)])


def test_cli_analyze_rejects_unknown_group_column(results: Path):
    with pytest.raises(SystemExit, match="not found"):
        main(["analyze", "--config", str(results), "--by", "nonexistent"])


def test_cli_design_writes_loadable_lists(experiment: Path, capsys):
    cfg = experiment.read_text().replace("trial_lists: lists", "trial_lists: generated")
    experiment.write_text(cfg + "design:\n  seed: 3\n  n_participants: 2\n  repetitions: 2\n"
                          "  training: {filter: {reconstruction: measured}, n_trials: 2}\n")
    main(["design", "--config", str(experiment)])
    assert sorted(p.name for p in (experiment.parent / "generated").iterdir()) == ["P01.csv", "P02.csv"]
    main(["check", "--config", str(experiment)])
    assert "OK" in capsys.readouterr().out
