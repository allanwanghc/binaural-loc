"""Stimulus manifest and trial lists."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .wavinfo import read_wav_info

MANIFEST_REQUIRED = ("stimulus_id", "file_path", "target_azimuth", "target_elevation")
TRIAL_LIST_COLUMNS = ("participant_id", "block", "trial_index", "stimulus_id", "is_training", "is_catch", "list_seed")

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ExperimentError(ValueError):
    pass


def check_id(value: str, what: str) -> str:
    """IDs end up in file names."""
    if not ID_PATTERN.match(value or ""):
        raise ExperimentError(f"invalid {what} {value!r}: use letters, digits, '_' or '-' (max 64)")
    return value


def parse_bool(value: str, where: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no", ""):
        return False
    raise ExperimentError(f"{where}: cannot read {value!r} as a boolean")


@dataclass(frozen=True)
class Stimulus:
    stimulus_id: str
    path: Path
    target_azimuth: float
    target_elevation: float
    metadata: dict[str, str]  # all manifest columns


def load_manifest(path: Path, sample_rate: int, check_audio: bool = True) -> dict[str, Stimulus]:
    if not path.is_file():
        raise ExperimentError(f"manifest not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [c.strip() for c in reader.fieldnames or []]
        missing = [c for c in MANIFEST_REQUIRED if c not in cols]
        if missing:
            raise ExperimentError(f"{path.name}: missing required column(s) {missing}")
        stimuli: dict[str, Stimulus] = {}
        for line_no, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
            sid = row["stimulus_id"]
            where = f"{path.name} line {line_no}"
            if not sid:
                raise ExperimentError(f"{where}: empty stimulus_id")
            if sid in stimuli:
                raise ExperimentError(f"{where}: duplicate stimulus_id {sid!r}")
            try:
                az, el = float(row["target_azimuth"]), float(row["target_elevation"])
            except ValueError:
                raise ExperimentError(f"{where}: target_azimuth/target_elevation must be numbers") from None
            if not -90 <= el <= 90:
                raise ExperimentError(f"{where}: target_elevation {el} outside [-90, 90]")
            wav = Path(row["file_path"]).expanduser()
            if not wav.is_absolute():
                wav = (path.parent / wav).resolve()
            if check_audio:
                check_wav(wav, sample_rate, where)
            stimuli[sid] = Stimulus(sid, wav, az, el, row)
    if not stimuli:
        raise ExperimentError(f"{path.name}: no stimuli")
    return stimuli


def check_wav(path: Path, sample_rate: int, where: str = "") -> None:
    prefix = f"{where}: " if where else ""
    if not path.is_file():
        raise ExperimentError(f"{prefix}file not found: {path}")
    info = read_wav_info(path)
    if info.sample_rate != sample_rate:
        raise ExperimentError(f"{prefix}{path.name} is {info.sample_rate} Hz, config sample_rate is {sample_rate} Hz")
    if info.channels != 2:
        raise ExperimentError(f"{prefix}{path.name} has {info.channels} channel(s), binaural stimuli need 2")


@dataclass(frozen=True)
class Trial:
    participant_id: str
    block: int
    trial_index: int
    stimulus_id: str
    is_training: bool
    is_catch: bool
    list_seed: str


def find_trial_list(folder: Path, participant_id: str, session_id: str) -> Path:
    """`<pid>_<sid>.csv` if present, otherwise `<pid>.csv`."""
    for name in (f"{participant_id}_{session_id}.csv", f"{participant_id}.csv"):
        if (folder / name).is_file():
            return folder / name
    raise ExperimentError(
        f"no trial list for participant {participant_id!r} (looked for {participant_id}_{session_id}.csv "
        f"and {participant_id}.csv in {folder})"
    )


def load_trial_list(path: Path, stimuli: dict[str, Stimulus], participant_id: str | None = None) -> list[Trial]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [c.strip() for c in reader.fieldnames or []]
        missing = [c for c in TRIAL_LIST_COLUMNS if c not in cols]
        if missing:
            raise ExperimentError(f"{path.name}: missing column(s) {missing}")
        trials = []
        for line_no, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
            where = f"{path.name} line {line_no}"
            try:
                block, index = int(row["block"]), int(row["trial_index"])
            except ValueError:
                raise ExperimentError(f"{where}: block and trial_index must be integers") from None
            if row["stimulus_id"] not in stimuli:
                raise ExperimentError(f"{where}: stimulus_id {row['stimulus_id']!r} not in manifest")
            if participant_id is not None and row["participant_id"] != participant_id:
                raise ExperimentError(f"{where}: participant_id {row['participant_id']!r}, expected {participant_id!r}")
            trials.append(
                Trial(
                    participant_id=row["participant_id"],
                    block=block,
                    trial_index=index,
                    stimulus_id=row["stimulus_id"],
                    is_training=parse_bool(row["is_training"], where),
                    is_catch=parse_bool(row["is_catch"], where),
                    list_seed=row["list_seed"],
                )
            )
    if not trials:
        raise ExperimentError(f"{path.name}: no trials")
    trials.sort(key=lambda t: t.trial_index)
    seen = set()
    for t in trials:
        if t.trial_index in seen:
            raise ExperimentError(f"{path.name}: duplicate trial_index {t.trial_index}")
        seen.add(t.trial_index)
    return trials


def audio_token(participant_id: str, session_id: str, stimulus_id: str) -> str:
    """File name shown to the browser. Does not change when the server restarts."""
    h = hashlib.sha256(f"{participant_id}|{session_id}|{stimulus_id}".encode()).hexdigest()
    return f"s_{h[:12]}"
