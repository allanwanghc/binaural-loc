from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RESPONSE_MODES = ("azimuth_only", "azimuth_elevation")

DEFAULT_EXTERNALIZATION_LABELS = [
    "Inside my head",
    "At the surface of my head",
    "Outside, close to my head",
    "Outside, far from my head",
]

# can be overridden under `text:`
DEFAULT_TEXT = {
    "volume": (
        "Put on the headphones. You will hear a reference sound. "
        "Please do not change the volume during the experiment."
    ),
    "tutorial": (
        "After each sound, show where it came from. "
        "In the left picture (the head seen from above), click on the circle in the direction of the sound, "
        "including whether it was in front of you or behind you. "
        "In the right picture, the half-circle points in the direction you chose; click on it to show how high "
        "or low the sound was. You can change both answers until you press Confirm. "
        "The size of the circles does not mean distance: only the direction matters. "
        "Try it now."
    ),
    "tutorial_azimuth_only": (
        "After each sound, show where it came from. "
        "Click on the circle around the head (seen from above) in the direction of the sound, "
        "including whether it was in front of you or behind you. You can change your answer until you press Confirm. "
        "The size of the circle does not mean distance: only the direction matters. "
        "Try it now."
    ),
    "externalization": "Also tell us where the sound seemed to be: inside your head or outside it.",
    "training_intro": (
        "First, a short practice. After each answer, the correct direction is shown in green."
    ),
    "main_intro": "The practice is finished. From now on, no correct answers will be shown.",
    "rest": "Time for a short break. Please keep the headphones on, or put them back on the same way.",
    "end": "The experiment is finished. Thank you!",
}


class ConfigError(ValueError):
    pass


@dataclass
class ResponseConfig:
    mode: str = "azimuth_elevation"
    externalization: str = "off"  # "off" | "rating"
    externalization_labels: list[str] = field(default_factory=lambda: list(DEFAULT_EXTERNALIZATION_LABELS))


@dataclass
class Config:
    path: Path
    title: str
    sample_rate: int
    manifest: Path
    trial_lists: Path
    results: Path
    volume_reference: Path | None
    max_replays: int
    rest_min_seconds: float
    response: ResponseConfig
    text: dict[str, str]
    design: dict[str, Any] | None = None  # parsed by binaural_loc.design

    def public(self) -> dict[str, Any]:
        """What the browser gets. No paths, no condition information."""
        return {
            "title": self.title,
            "sample_rate": self.sample_rate,
            "max_replays": self.max_replays,
            "rest_min_seconds": self.rest_min_seconds,
            "response": {
                "mode": self.response.mode,
                "externalization": self.response.externalization,
                "externalization_labels": self.response.externalization_labels,
            },
            "text": self.text,
        }


def _resolve(base: Path, value: Any, key: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"`{key}` must be a path")
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError("config must be a YAML mapping")
    base = path.parent

    for key in ("manifest", "trial_lists"):
        if key not in raw:
            raise ConfigError(f"missing required key `{key}`")

    resp_raw = raw.get("response") or {}
    ext = resp_raw.get("externalization", "off")
    if ext is False or ext is None:  # YAML parses a bare `off` as False
        ext = "off"
    resp = ResponseConfig(
        mode=resp_raw.get("mode", "azimuth_elevation"),
        externalization=str(ext),
        externalization_labels=list(resp_raw.get("externalization_labels") or DEFAULT_EXTERNALIZATION_LABELS),
    )
    if resp.mode not in RESPONSE_MODES:
        raise ConfigError(f"response.mode must be one of {RESPONSE_MODES}, got {resp.mode!r}")
    if resp.externalization not in ("off", "rating"):
        raise ConfigError(f"response.externalization must be 'off' or 'rating', got {resp.externalization!r}")
    if len(resp.externalization_labels) < 2:
        raise ConfigError("response.externalization_labels needs at least 2 labels")

    max_replays = raw.get("max_replays", 0)
    if not isinstance(max_replays, int) or max_replays < 0:
        raise ConfigError("max_replays must be an integer >= 0")

    rest = raw.get("rest") or {}
    rest_min = float(rest.get("min_seconds", 20))
    if rest_min < 0:
        raise ConfigError("rest.min_seconds must be >= 0")

    sample_rate = raw.get("sample_rate", 48000)
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ConfigError("sample_rate must be a positive integer")

    text = dict(DEFAULT_TEXT)
    for k, v in (raw.get("text") or {}).items():
        if k not in DEFAULT_TEXT:
            raise ConfigError(f"unknown text key `{k}` (known: {', '.join(DEFAULT_TEXT)})")
        text[k] = str(v).strip()

    return Config(
        path=path,
        title=str(raw.get("title", "Listening test")),
        sample_rate=sample_rate,
        manifest=_resolve(base, raw["manifest"], "manifest"),
        trial_lists=_resolve(base, raw["trial_lists"], "trial_lists"),
        results=_resolve(base, raw.get("results", "results"), "results"),
        volume_reference=_resolve(base, raw["volume_reference"], "volume_reference") if raw.get("volume_reference") else None,
        max_replays=max_replays,
        rest_min_seconds=rest_min,
        response=resp,
        text=text,
        design=raw.get("design"),
    )
