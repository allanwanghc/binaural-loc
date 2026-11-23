from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from binaural_loc.design.trial_lists import build_trial_list, parse_design, participant_seed, write_trial_lists
from binaural_loc.experiment import ExperimentError, Stimulus, load_trial_list


def stimuli() -> dict[str, Stimulus]:
    out = {}
    for cond in ("measured", "uniform", "random"):
        for az in (0, 60, 120, 180, 240, 300):
            sid = f"{cond}_{az}"
            out[sid] = Stimulus(sid, Path(f"{sid}.wav"), az, 0, {"stimulus_id": sid, "method": cond})
    for k in range(2):
        out[f"catch_{k}"] = Stimulus(f"catch_{k}", Path("c.wav"), 0, 0, {"stimulus_id": f"catch_{k}", "method": "catch"})
    return out


BASE = {
    "seed": 7,
    "participants": ["P01", "P02", "P03"],
    "repetitions": 3,
    "training": {"filter": {"method": "measured"}, "n_trials": 5},
    "catch": {"filter": {"method": "catch"}, "per_block": 2},
}


def test_participant_ids():
    assert parse_design({"seed": 1, "n_participants": 3}).participants == ["P01", "P02", "P03"]
    assert parse_design({"seed": 1, "n_participants": 120}).participants[0] == "P001"
    with pytest.raises(ExperimentError):
        parse_design({"seed": 1, "participants": ["P01", "P01"]})
    with pytest.raises(ExperimentError):
        parse_design({"participants": ["P01"]})  # no seed


def test_structure_mixed_blocks():
    d = parse_design(BASE)
    rows = build_trial_list(d, stimuli(), 0)
    assert [r["trial_index"] for r in rows] == list(range(len(rows)))
    train = [r for r in rows if r["is_training"]]
    assert len(train) == 5 and all(r["block"] == 0 for r in train)
    assert all(r["stimulus_id"].startswith("measured") for r in train)
    assert rows[:5] == train  # training first
    for block in (1, 2, 3):
        b = [r for r in rows if r["block"] == block]
        main = Counter(r["stimulus_id"] for r in b if not r["is_catch"])
        assert len(main) == 18 and set(main.values()) == {1}  # every main stimulus exactly once
        catch = [r for r in b if r["is_catch"]]
        assert len(catch) == 2 and all(r["stimulus_id"].startswith("catch") for r in catch)
    assert not any(r["stimulus_id"].startswith("catch") and not r["is_catch"] for r in rows)


def test_blocks_per_repetition_split():
    # without a catch filter, catch stimuli would be ordinary main stimuli, so restrict main
    d = parse_design({**BASE, "repetitions": 2, "blocks_per_repetition": 3, "catch": None,
                      "main": {"filter": {"method": ["measured", "uniform", "random"]}}})
    rows = [r for r in build_trial_list(d, stimuli(), 0) if not r["is_training"]]
    assert sorted({r["block"] for r in rows}) == [1, 2, 3, 4, 5, 6]
    first_rep = [r["stimulus_id"] for r in rows if r["block"] in (1, 2, 3)]
    assert sorted(first_rep) == sorted(s for s in stimuli() if not s.startswith("catch"))
    assert [sum(r["block"] == b for r in rows) for b in range(1, 7)] == [6] * 6


def test_reproducible_and_independent():
    d = parse_design(BASE)
    a = build_trial_list(d, stimuli(), 0)
    assert a == build_trial_list(parse_design(BASE), stimuli(), 0)
    b = build_trial_list(d, stimuli(), 1)
    assert [r["stimulus_id"] for r in a] != [r["stimulus_id"] for r in b]
    c = build_trial_list(parse_design({**BASE, "seed": 8}), stimuli(), 0)
    assert [r["stimulus_id"] for r in a] != [r["stimulus_id"] for r in c]
    assert {r["list_seed"] for r in a} == {participant_seed(7, 0)}
    # adding participants later does not change existing lists
    more = parse_design({**BASE, "participants": ["P01", "P02", "P03", "P04"]})
    assert build_trial_list(more, stimuli(), 0) == a


def test_filters():
    with pytest.raises(ExperimentError, match="no column"):
        build_trial_list(parse_design({**BASE, "main": {"filter": {"nope": "x"}}}), stimuli(), 0)
    with pytest.raises(ExperimentError, match="matches no stimuli"):
        build_trial_list(parse_design({**BASE, "training": {"filter": {"method": "x"}, "n_trials": 2}}), stimuli(), 0)
    only = parse_design({**BASE, "main": {"filter": {"method": ["uniform", "random"]}}, "catch": None})
    rows = [r for r in build_trial_list(only, stimuli(), 0) if not r["is_training"]]
    assert {r["stimulus_id"].split("_")[0] for r in rows} == {"uniform", "random"}


def test_training_draws_with_replacement_when_needed():
    d = parse_design({**BASE, "training": {"filter": {"method": "measured"}, "n_trials": 10}})
    assert sum(r["is_training"] for r in build_trial_list(d, stimuli(), 0)) == 10


def test_write_is_safe(tmp_path: Path):
    stim = stimuli()
    d = parse_design(BASE)
    rep = write_trial_lists(d, stim, tmp_path)
    assert len(rep["written"]) == 3
    trials = load_trial_list(tmp_path / "P02.csv", stim, participant_id="P02")  # readable by the server
    assert trials[0].is_training and sum(t.is_catch for t in trials) == 6

    rep = write_trial_lists(parse_design({**BASE, "participants": ["P01", "P02", "P03", "P04"]}), stim, tmp_path)
    assert [p.stem for p in rep["written"]] == ["P04"] and len(rep["unchanged"]) == 3

    with pytest.raises(ExperimentError, match="would change"):
        write_trial_lists(parse_design({**BASE, "seed": 99}), stim, tmp_path)
    rep = write_trial_lists(parse_design({**BASE, "seed": 99}), stim, tmp_path, overwrite=True)
    assert len(rep["overwritten"]) == 3
