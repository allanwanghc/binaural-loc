"""Trial lists: training block, then mixed main blocks with optional catch trials."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..experiment import TRIAL_LIST_COLUMNS, ExperimentError, Stimulus, check_id


@dataclass
class Design:
    seed: int
    participants: list[str]
    repetitions: int = 1
    blocks_per_repetition: int = 1
    main_filter: dict[str, list[str]] = field(default_factory=dict)
    training_filter: dict[str, list[str]] | None = None
    training_trials: int = 0
    catch_filter: dict[str, list[str]] | None = None
    catch_per_block: int = 0


def _filter(raw: Any, where: str) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ExperimentError(f"{where}.filter must be a mapping column -> value(s)")
    return {str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in raw.items()}


def parse_design(raw: dict[str, Any]) -> Design:
    if not isinstance(raw, dict):
        raise ExperimentError("config has no `design:` section")
    if "seed" not in raw or not isinstance(raw["seed"], int):
        raise ExperimentError("design.seed must be an integer")
    if "participants" in raw:
        participants = [str(p) for p in raw["participants"]]
    elif "n_participants" in raw:
        n = int(raw["n_participants"])
        participants = [f"P{i:0{max(2, len(str(n)))}d}" for i in range(1, n + 1)]
    else:
        raise ExperimentError("design needs `participants` or `n_participants`")
    for p in participants:
        check_id(p, "participant ID")
    if len(set(participants)) != len(participants):
        raise ExperimentError("design.participants contains duplicates")

    d = Design(seed=raw["seed"], participants=participants)
    d.repetitions = int(raw.get("repetitions", 1))
    d.blocks_per_repetition = int(raw.get("blocks_per_repetition", 1))
    if d.repetitions < 1 or d.blocks_per_repetition < 1:
        raise ExperimentError("design.repetitions and blocks_per_repetition must be >= 1")
    d.main_filter = _filter((raw.get("main") or {}).get("filter"), "design.main")
    if raw.get("training"):
        d.training_filter = _filter(raw["training"].get("filter"), "design.training")
        d.training_trials = int(raw["training"].get("n_trials", 0))
    if raw.get("catch"):
        d.catch_filter = _filter(raw["catch"].get("filter"), "design.catch")
        d.catch_per_block = int(raw["catch"].get("per_block", 0))
    return d


def _select(stimuli: dict[str, Stimulus], flt: dict[str, list[str]], where: str) -> list[str]:
    for col in flt:
        if any(col not in s.metadata for s in stimuli.values()):
            raise ExperimentError(f"{where}.filter: manifest has no column {col!r}")
    ids = [sid for sid, s in stimuli.items() if all(s.metadata[c] in vals for c, vals in flt.items())]
    if not ids:
        raise ExperimentError(f"{where}.filter matches no stimuli")
    return sorted(ids)


def participant_seed(master_seed: int, index: int) -> int:
    return int(np.random.SeedSequence([master_seed, index]).generate_state(1)[0])


def build_trial_list(design: Design, stimuli: dict[str, Stimulus], participant_index: int) -> list[dict[str, Any]]:
    pid = design.participants[participant_index]
    seed = participant_seed(design.seed, participant_index)
    rng = np.random.default_rng(seed)

    catch = _select(stimuli, design.catch_filter, "design.catch") if design.catch_filter is not None else []
    main = [s for s in _select(stimuli, design.main_filter, "design.main") if s not in set(catch)]
    if not main:
        raise ExperimentError("no main stimuli left after removing catch stimuli")

    plan: list[tuple[int, str, bool, bool]] = []  # (block, stimulus, training, catch)
    if design.training_filter is not None and design.training_trials > 0:
        pool = _select(stimuli, design.training_filter, "design.training")
        replace = design.training_trials > len(pool)
        for sid in rng.choice(pool, design.training_trials, replace=replace):
            plan.append((0, str(sid), True, False))

    block = 0
    for _ in range(design.repetitions):
        order = [str(s) for s in rng.permutation(main)]
        for chunk in np.array_split(np.array(order, dtype=object), design.blocks_per_repetition):
            block += 1
            items = [(str(s), False) for s in chunk]
            if catch and design.catch_per_block > 0:
                for sid in rng.choice(catch, design.catch_per_block, replace=design.catch_per_block > len(catch)):
                    items.insert(int(rng.integers(0, len(items) + 1)), (str(sid), True))
            plan.extend((block, s, False, is_catch) for s, is_catch in items)

    return [
        {
            "participant_id": pid,
            "block": b,
            "trial_index": i,
            "stimulus_id": sid,
            "is_training": int(tr),
            "is_catch": int(c),
            "list_seed": seed,
        }
        for i, (b, sid, tr, c) in enumerate(plan)
    ]


def _render(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(TRIAL_LIST_COLUMNS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def write_trial_lists(
    design: Design, stimuli: dict[str, Stimulus], folder: Path, overwrite: bool = False
) -> dict[str, list[Path]]:
    """Write one CSV per participant.

    Refuses to change existing lists unless `overwrite`, since they may belong
    to a running experiment.
    """
    folder.mkdir(parents=True, exist_ok=True)
    rendered = {folder / f"{pid}.csv": _render(build_trial_list(design, stimuli, i))
                for i, pid in enumerate(design.participants)}
    changed = [p for p, text in rendered.items() if p.exists() and p.read_text(encoding="utf-8") != text]
    if changed and not overwrite:
        raise ExperimentError(
            f"{len(changed)} existing trial list(s) would change (e.g. {changed[0].name}): the design, seed or "
            "manifest differs from when they were made. Use --force only if no participant has started."
        )
    report: dict[str, list[Path]] = {"written": [], "unchanged": [], "overwritten": []}
    for path, text in rendered.items():
        if path.exists() and path not in changed:
            report["unchanged"].append(path)
            continue
        report["overwritten" if path in changed else "written"].append(path)
        path.write_text(text, encoding="utf-8")
    return report
