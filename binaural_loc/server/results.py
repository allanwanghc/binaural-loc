from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class JsonlLog:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a+b") as f:
                # a crash may have left a line without newline
                f.seek(0, os.SEEK_END)
                if f.tell() > 0:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        line = "\n" + line
                f.write((line + "\n").encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())

    def read(self) -> list[dict[str, Any]]:
        """All complete records, skipping a line cut off by a crash."""
        if not self.path.is_file():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out


def results_paths(results_dir: Path, participant_id: str, session_id: str) -> tuple[Path, Path]:
    stem = f"{participant_id}_{session_id}"
    return results_dir / f"{stem}.jsonl", results_dir / f"{stem}.events.jsonl"
