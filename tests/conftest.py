from __future__ import annotations

import csv
import wave
from pathlib import Path

import numpy as np
import pytest


def write_wav(path: Path, fs: int = 48000, channels: int = 2, n: int = 480) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.zeros((n, channels)) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(data.tobytes())


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def experiment(tmp_path: Path) -> Path:
    """A tiny experiment: 3 stimuli (one per condition), P01 with 1 training + 3 main trials."""
    stim = tmp_path / "stimuli"
    conds = [("measured", 0.0, 0.0), ("uniform_pca", 90.0, 30.0), ("random_nf", 225.0, -20.0)]
    rows = []
    for i, (cond, az, el) in enumerate(conds):
        write_wav(stim / f"{cond}_{i}.wav")
        rows.append({"stimulus_id": f"{cond}_az{az:g}", "file_path": f"{cond}_{i}.wav",
                     "target_azimuth": az, "target_elevation": el, "reconstruction": cond})
    write_csv(stim / "manifest.csv", rows)
    write_wav(stim / "ref.wav")
    trials = [
        (0, 0, "measured_az0", 1, 0),
        (1, 1, "uniform_pca_az90", 0, 0),
        (1, 2, "random_nf_az225", 0, 1),
        (2, 3, "measured_az0", 0, 0),
    ]
    write_csv(tmp_path / "lists" / "P01.csv", [
        {"participant_id": "P01", "block": b, "trial_index": i, "stimulus_id": s,
         "is_training": tr, "is_catch": c, "list_seed": 42}
        for b, i, s, tr, c in trials
    ])
    (tmp_path / "experiment.yaml").write_text(
        "title: Test\n"
        "sample_rate: 48000\n"
        "manifest: stimuli/manifest.csv\n"
        "trial_lists: lists\n"
        "results: results\n"
        "volume_reference: stimuli/ref.wav\n"
        "max_replays: 1\n"
        "response:\n"
        "  mode: azimuth_elevation\n"
        "  externalization: off\n"
    )
    return tmp_path / "experiment.yaml"
