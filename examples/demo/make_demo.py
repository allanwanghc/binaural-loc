"""Demo stimuli: noise bursts with a simple ITD/ILD model.

No HRTF, so front/back and elevation cannot be heard.
"""

from __future__ import annotations

import csv
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FS = 48_000
DURATION_S = 0.4
RAMP_S = 0.01
HEAD_RADIUS_M = 0.0875
SPEED_OF_SOUND = 343.0
MAX_ILD_DB = 10.0
RMS_DBFS = -20.0
AZIMUTHS = [0, 45, 90, 135, 180, 225, 270, 315]  # SOFA: +90 = left
CONDITIONS = {"itd_ild": True, "ild_only": False}  # name -> use ITD


def render(azimuth_deg: float, use_itd: bool, rng: np.random.Generator) -> np.ndarray:
    n = int(FS * DURATION_S)
    noise = rng.standard_normal(n)
    lateral = np.arcsin(np.sin(np.deg2rad(azimuth_deg)))  # + = left
    itd = HEAD_RADIUS_M / SPEED_OF_SOUND * (abs(lateral) + np.sin(abs(lateral))) if use_itd else 0.0
    delay = int(round(itd * FS))
    g = 10 ** (MAX_ILD_DB * np.sin(lateral) / 40)  # half of the ILD on each ear
    near, far = noise, np.concatenate([np.zeros(delay), noise[: n - delay]])
    left, right = (near * g, far / g) if lateral >= 0 else (far * g, near / g)
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, int(FS * RAMP_S))))
    env = np.ones(n)
    env[: ramp.size], env[-ramp.size :] = ramp, ramp[::-1]
    x = np.stack([left * env, right * env], axis=1)
    return x * 10 ** (RMS_DBFS / 20) / np.sqrt(np.mean(x**2))


def write_wav(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(np.round(np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    rng = np.random.default_rng(1)
    stim_dir = HERE / "stimuli"
    stim_dir.mkdir(exist_ok=True)

    manifest = []
    for cond, use_itd in CONDITIONS.items():
        for az in AZIMUTHS:
            sid = f"{cond}_az{az:03d}"
            write_wav(stim_dir / f"{sid}.wav", render(az, use_itd, rng))
            manifest.append({"stimulus_id": sid, "file_path": f"{sid}.wav", "target_azimuth": az,
                             "target_elevation": 0, "condition": cond, "uses_itd": int(use_itd)})
    write_wav(stim_dir / "reference.wav", render(0, True, rng))
    write_csv(stim_dir / "manifest.csv", manifest)
    print(f"{len(manifest)} stimuli + manifest in {stim_dir}")


if __name__ == "__main__":
    main()
