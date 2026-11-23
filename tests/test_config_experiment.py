from __future__ import annotations

from pathlib import Path

import pytest

from binaural_loc.config import ConfigError, load_config
from binaural_loc.experiment import (
    ExperimentError,
    audio_token,
    check_id,
    find_trial_list,
    load_manifest,
    load_trial_list,
)
from binaural_loc.wavinfo import read_wav_info

from .conftest import write_csv, write_wav


def test_config_defaults_and_paths(experiment: Path):
    cfg = load_config(experiment)
    assert cfg.manifest == experiment.parent / "stimuli" / "manifest.csv"
    assert cfg.response.externalization == "off"  # bare YAML `off` is parsed as False
    assert cfg.max_replays == 1
    assert cfg.rest_min_seconds == 20
    assert "Inside my head" in cfg.response.externalization_labels


def test_public_config_has_no_paths(experiment: Path):
    pub = load_config(experiment).public()
    flat = repr(pub)
    assert "manifest" not in flat and "stimuli" not in flat and str(experiment.parent) not in flat


@pytest.mark.parametrize(
    "extra, msg",
    [
        ("response:\n  mode: sphere\n", "response.mode"),
        ("response:\n  externalization: yes\n", "externalization"),
        ("max_replays: -1\n", "max_replays"),
        ("text:\n  nonsense: hi\n", "unknown text key"),
    ],
)
def test_config_errors(tmp_path: Path, extra: str, msg: str):
    p = tmp_path / "e.yaml"
    p.write_text("manifest: m.csv\ntrial_lists: l\n" + extra)
    with pytest.raises(ConfigError, match=msg):
        load_config(p)


def test_text_override(tmp_path: Path):
    p = tmp_path / "e.yaml"
    p.write_text("manifest: m.csv\ntrial_lists: l\ntext:\n  end: 谢谢！\n")
    cfg = load_config(p)
    assert cfg.text["end"] == "谢谢！"
    assert cfg.text["rest"]  # defaults kept


def test_manifest_keeps_extra_columns(experiment: Path):
    stim = load_manifest(experiment.parent / "stimuli" / "manifest.csv", 48000)
    s = stim["uniform_pca_az90"]
    assert (s.target_azimuth, s.target_elevation) == (90.0, 30.0)
    assert s.metadata["reconstruction"] == "uniform_pca"


def test_manifest_rejects_wrong_rate_and_mono(tmp_path: Path):
    write_wav(tmp_path / "a.wav", fs=44100)
    write_csv(tmp_path / "m.csv", [{"stimulus_id": "a", "file_path": "a.wav", "target_azimuth": 0, "target_elevation": 0}])
    with pytest.raises(ExperimentError, match="44100 Hz"):
        load_manifest(tmp_path / "m.csv", 48000)
    write_wav(tmp_path / "a.wav", channels=1)
    with pytest.raises(ExperimentError, match="1 channel"):
        load_manifest(tmp_path / "m.csv", 48000)


def test_manifest_missing_column_and_duplicates(tmp_path: Path):
    write_csv(tmp_path / "m.csv", [{"stimulus_id": "a", "file_path": "a.wav", "target_azimuth": 0}])
    with pytest.raises(ExperimentError, match="target_elevation"):
        load_manifest(tmp_path / "m.csv", 48000, check_audio=False)
    row = {"stimulus_id": "a", "file_path": "a.wav", "target_azimuth": 0, "target_elevation": 0}
    write_csv(tmp_path / "m.csv", [row, row])
    with pytest.raises(ExperimentError, match="duplicate"):
        load_manifest(tmp_path / "m.csv", 48000, check_audio=False)


def test_trial_list_loading_and_errors(experiment: Path):
    base = experiment.parent
    stim = load_manifest(base / "stimuli" / "manifest.csv", 48000)
    trials = load_trial_list(base / "lists" / "P01.csv", stim, participant_id="P01")
    assert [t.trial_index for t in trials] == [0, 1, 2, 3]
    assert trials[0].is_training and not trials[1].is_training and trials[2].is_catch
    with pytest.raises(ExperimentError, match="expected 'P02'"):
        load_trial_list(base / "lists" / "P01.csv", stim, participant_id="P02")

    row = {"participant_id": "P01", "block": 1, "trial_index": 0, "stimulus_id": "nope",
           "is_training": 0, "is_catch": 0, "list_seed": 1}
    write_csv(base / "bad.csv", [row])
    with pytest.raises(ExperimentError, match="not in manifest"):
        load_trial_list(base / "bad.csv", stim)
    write_csv(base / "bad.csv", [{**row, "stimulus_id": "measured_az0"}] * 2)
    with pytest.raises(ExperimentError, match="duplicate trial_index"):
        load_trial_list(base / "bad.csv", stim)


def test_find_trial_list_prefers_session_specific(experiment: Path):
    lists = experiment.parent / "lists"
    assert find_trial_list(lists, "P01", "S1").name == "P01.csv"
    (lists / "P01_S2.csv").write_text((lists / "P01.csv").read_text())
    assert find_trial_list(lists, "P01", "S2").name == "P01_S2.csv"
    with pytest.raises(ExperimentError):
        find_trial_list(lists, "P99", "S1")


@pytest.mark.parametrize("bad", ["", "../x", "a b", "P/1", "x" * 65])
def test_check_id_rejects_unsafe(bad: str):
    with pytest.raises(ExperimentError):
        check_id(bad, "participant ID")


def test_audio_token_is_opaque_and_stable():
    t = audio_token("P01", "S1", "uniform_pca_az90")
    assert t == audio_token("P01", "S1", "uniform_pca_az90")
    assert t != audio_token("P02", "S1", "uniform_pca_az90")
    assert t.startswith("s_") and "uniform" not in t and "90" not in t[:2]


def test_wavinfo_skips_other_chunks(tmp_path: Path):
    import struct

    fmt = struct.pack("<HHIIHH", 3, 2, 48000, 48000 * 8, 8, 32)
    data = b"RIFF" + b"\0\0\0\0" + b"WAVE" + b"LIST" + struct.pack("<I", 3) + b"abc\0" + b"fmt " + struct.pack("<I", 16) + fmt
    (tmp_path / "f.wav").write_bytes(data)
    info = read_wav_info(tmp_path / "f.wav")
    assert (info.sample_rate, info.channels) == (48000, 2)
