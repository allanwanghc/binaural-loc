"""Results + manifest -> one row per trial."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .metrics import add_trial_metrics

RESULT_KEYS = ("participant_id", "session_id", "trial_index")


def read_results(results_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        if path.name.endswith(".events.jsonl"):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # torn last line after a crash
    df = pd.DataFrame(rows)
    if not df.empty and df.duplicated(list(RESULT_KEYS)).any():
        dups = df[df.duplicated(list(RESULT_KEYS), keep=False)][list(RESULT_KEYS)]
        raise ValueError(f"duplicate trials in results:\n{dups.to_string(index=False)}")
    return df


def read_manifest(path: Path) -> pd.DataFrame:
    # read as text so IDs like "007" survive
    m = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    m.columns = [c.strip() for c in m.columns]
    for c in ("target_azimuth", "target_elevation"):
        m[c] = pd.to_numeric(m[c])
    return m


def merge(
    results_dir: Path,
    manifest_path: Path,
    include_training: bool = False,
    include_catch: bool = False,
    **metric_kwargs: float,
) -> pd.DataFrame:
    """Manifest columns that clash with result columns get a `stim_` prefix."""
    res = read_results(results_dir)
    if res.empty:
        raise ValueError(f"no results in {results_dir}")
    man = read_manifest(manifest_path)
    clash = (set(man.columns) & set(res.columns)) - {"stimulus_id"}
    man = man.rename(columns={c: f"stim_{c}" for c in clash})

    unknown = set(res["stimulus_id"]) - set(man["stimulus_id"])
    if unknown:
        raise ValueError(f"results contain stimulus_ids missing from the manifest: {sorted(unknown)[:10]}")
    df = res.merge(man, on="stimulus_id", how="left", validate="many_to_one")

    if not include_training:
        df = df[~df["is_training"].astype(bool)]
    if not include_catch:
        df = df[~df["is_catch"].astype(bool)]
    df = add_trial_metrics(df.reset_index(drop=True), **metric_kwargs)
    return df.sort_values(list(RESULT_KEYS), kind="stable").reset_index(drop=True)
