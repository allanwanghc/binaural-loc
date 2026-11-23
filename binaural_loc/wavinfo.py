"""Read sample rate and channel count from a WAV header (also works for float WAVs)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int


def read_wav_info(path: str | Path) -> WavInfo:
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError(f"{path}: not a RIFF/WAVE file")
        while True:
            chunk = f.read(8)
            if len(chunk) < 8:
                raise ValueError(f"{path}: no fmt chunk")
            cid, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if cid == b"fmt ":
                _format, channels, rate = struct.unpack("<HHI", f.read(8))
                return WavInfo(sample_rate=rate, channels=channels)
            f.seek(size + (size % 2), 1)
