"""Error metrics per trial and summaries per group.

Interaural-polar metrics follow Middlebrooks (1999), JASA 106(3), i.e.
querrMiddlebrooks and rmsPmedianlocal in AMT's localizationerror, not the
laterally weighted 45 deg criterion of AMT's querr. See the README for the
full list of definitions.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .coords import (
    angle_from_frontal_plane,
    great_circle_error,
    mirror_front_back,
    sph_to_cart,
    to_interaural_polar,
    wrap_angle,
)

POLAR_LATERAL_RANGE = 30.0
QUADRANT_THRESHOLD = 90.0
FRONT_BACK_MARGIN = 10.0

# asin(sin(210 deg)) is -30.00000000000001, so compare with limits loosely
TOL = 1e-6

# column -> signed error? (then the mean is the bias)
METRICS: dict[str, bool] = {
    "azimuth_error": True,
    "azimuth_error_abs": False,
    "elevation_error": True,
    "elevation_error_abs": False,
    "great_circle_error": False,
    "lateral_error": True,
    "lateral_error_abs": False,
    "local_polar_error": True,
    "quadrant_error": False,
    "front_back_confusion": False,
    "azimuth_error_fb_resolved": True,
    "great_circle_error_fb_resolved": False,
    "rt_ms": False,
    "response_externalization": False,
}


def add_trial_metrics(
    df: pd.DataFrame,
    polar_lateral_range: float = POLAR_LATERAL_RANGE,
    quadrant_threshold: float = QUADRANT_THRESHOLD,
    front_back_margin: float = FRONT_BACK_MARGIN,
) -> pd.DataFrame:
    """Copy of `df` with error columns.

    A missing response_elevation (azimuth-only sessions) counts as 0 deg for the
    spatial metrics; elevation_error is then NaN.
    """
    out = df.copy()
    t_az = out["target_azimuth"].to_numpy(dtype=float)
    t_el = out["target_elevation"].to_numpy(dtype=float)
    r_az = out["response_azimuth"].to_numpy(dtype=float)
    r_el_raw = pd.to_numeric(out["response_elevation"], errors="coerce").to_numpy(dtype=float)
    assumed = np.isnan(r_el_raw)
    r_el = np.where(assumed, 0.0, r_el_raw)
    out["response_elevation_assumed"] = assumed

    out["azimuth_error"] = wrap_angle(r_az - t_az)
    out["azimuth_error_abs"] = np.abs(out["azimuth_error"])
    out["elevation_error"] = np.where(assumed, np.nan, r_el - t_el)
    out["elevation_error_abs"] = np.abs(out["elevation_error"])
    out["great_circle_error"] = great_circle_error(t_az, t_el, r_az, r_el)

    t_lat, t_pol = to_interaural_polar(t_az, t_el)
    r_lat, r_pol = to_interaural_polar(r_az, r_el)
    out["target_lateral"], out["target_polar"] = t_lat, t_pol
    out["response_lateral"], out["response_polar"] = r_lat, r_pol
    out["lateral_error"] = r_lat - t_lat
    out["lateral_error_abs"] = np.abs(r_lat - t_lat)
    in_range = np.abs(t_lat) <= polar_lateral_range + TOL
    polar_err = np.where(in_range, wrap_angle(r_pol - t_pol), np.nan)
    out["polar_error"] = polar_err
    quadrant = np.abs(polar_err) > quadrant_threshold
    out["quadrant_error"] = np.where(in_range, quadrant.astype(float), np.nan)
    out["local_polar_error"] = np.where(in_range & ~quadrant, polar_err, np.nan)

    t_x = sph_to_cart(t_az, t_el)[..., 0]
    r_x = sph_to_cart(r_az, r_el)[..., 0]
    classifiable = angle_from_frontal_plane(t_az, t_el) >= front_back_margin - TOL
    confused = classifiable & (t_x * r_x < 0)
    out["front_back_confusion"] = np.where(classifiable, confused.astype(float), np.nan)
    m_az, m_el = mirror_front_back(r_az, r_el)
    res_az = np.where(confused, m_az, r_az)
    res_el = np.where(confused, m_el, r_el)
    out["azimuth_error_fb_resolved"] = wrap_angle(res_az - t_az)
    out["great_circle_error_fb_resolved"] = great_circle_error(t_az, t_el, res_az, res_el)
    return out


def _stats(x: pd.Series) -> dict[str, float]:
    v = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
    if v.size == 0:
        return {"n": 0, "mean": np.nan, "median": np.nan, "rms": np.nan, "sd": np.nan}
    return {
        "n": int(v.size),
        "mean": float(v.mean()),
        "median": float(np.median(v)),
        "rms": float(np.sqrt(np.mean(v**2))),
        "sd": float(v.std(ddof=1)) if v.size > 1 else np.nan,
    }


def summarize(
    trials: pd.DataFrame,
    by: Sequence[str] = ("participant_id",),
    metrics: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Long format: one row per group and metric with n, mean, median, rms, sd.

    For 0/1 columns (quadrant_error, front_back_confusion) the mean is the rate.
    """
    metrics = [m for m in (metrics or METRICS) if m in trials.columns]
    by = list(by)
    rows = []
    groups = trials.groupby(by, dropna=False, sort=True) if by else [((), trials)]
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        for m in metrics:
            rows.append({**dict(zip(by, key)), "metric": m, "signed": METRICS.get(m, False), **_stats(g[m])})
    return pd.DataFrame(rows)
