from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from binaural_loc.analysis.metrics import add_trial_metrics, summarize


def one(t_az, t_el, r_az, r_el, **kw):
    df = pd.DataFrame({"target_azimuth": [t_az], "target_elevation": [t_el],
                       "response_azimuth": [r_az], "response_elevation": [r_el]})
    return add_trial_metrics(df, **kw).iloc[0]


def test_small_elevation_error_is_local_polar():
    r = one(0, 0, 0, 20)
    assert r.elevation_error == pytest.approx(20)
    assert r.great_circle_error == pytest.approx(20)
    assert r.lateral_error == pytest.approx(0)
    assert r.local_polar_error == pytest.approx(20)
    assert r.quadrant_error == 0
    assert r.front_back_confusion == 0


def test_front_back_reversal():
    r = one(0, 0, 180, 0)
    assert r.azimuth_error == pytest.approx(-180)
    assert r.quadrant_error == 1
    assert np.isnan(r.local_polar_error)
    assert r.front_back_confusion == 1
    assert r.great_circle_error_fb_resolved == pytest.approx(0, abs=1e-6)
    assert r.azimuth_error_fb_resolved == pytest.approx(0, abs=1e-9)


def test_reversal_at_lateral_boundary_and_resolution():
    # target 30 deg left-front (lateral 30, inside the range), answer mirrored to the back
    r = one(30, 0, 150, 0)
    assert r.target_lateral == pytest.approx(30) and r.response_lateral == pytest.approx(30)
    assert r.lateral_error == pytest.approx(0, abs=1e-9)
    assert r.quadrant_error == 1
    assert r.front_back_confusion == 1
    assert r.great_circle_error == pytest.approx(120)
    assert r.great_circle_error_fb_resolved == pytest.approx(0, abs=1e-6)


def test_up_down_confusion_is_a_quadrant_error_but_not_front_back():
    r = one(0, 60, 0, -60)  # polar 60 vs -60 -> error 120
    assert r.quadrant_error == 1
    assert r.front_back_confusion == 0


def test_lateral_targets_excluded_from_polar_metrics():
    r = one(90, 0, 80, 10)  # target directly left: lateral 90
    assert np.isnan(r.polar_error) and np.isnan(r.quadrant_error) and np.isnan(r.local_polar_error)
    assert np.isnan(r.front_back_confusion)  # on the frontal plane
    assert not np.isnan(r.lateral_error)
    assert r.great_circle_error_fb_resolved == pytest.approx(r.great_circle_error)  # not mirrored


@pytest.mark.parametrize("az", [30, 150, 210, 330])
def test_lateral_limit_is_inclusive_on_both_sides(az):
    assert one(az, 0, az, 0).quadrant_error == 0  # exactly 30 deg lateral


@pytest.mark.parametrize("az", [80, 100, 260, 280])
def test_front_back_limit_is_inclusive_on_both_sides(az):
    assert one(az, 0, az, 0).front_back_confusion == 0  # exactly 10 deg from the frontal plane


def test_polar_range_is_a_parameter():
    r = one(60, 0, 120, 0, polar_lateral_range=60)
    assert r.quadrant_error == 1
    assert np.isnan(one(60, 0, 120, 0).quadrant_error)


def test_front_back_margin():
    assert np.isnan(one(85, 0, 95, 0).front_back_confusion)    # 5 deg from frontal plane
    assert np.isnan(one(0, 85, 180, 85).front_back_confusion)  # nearly overhead
    assert one(75, 0, 105, 0).front_back_confusion == 1        # 15 deg: classified
    assert one(85, 0, 95, 0, front_back_margin=0).front_back_confusion == 1


def test_azimuth_wraps_across_zero():
    r = one(350, 0, 10, 0)
    assert r.azimuth_error == pytest.approx(20)
    assert r.azimuth_error_abs == pytest.approx(20)


def test_azimuth_only_assumes_horizontal_response():
    r = one(30, 0, 40, None)
    assert bool(r.response_elevation_assumed)
    assert np.isnan(r.elevation_error)
    assert r.great_circle_error == pytest.approx(10)


def test_summarize_stats():
    df = pd.DataFrame({
        "participant_id": ["P01", "P01", "P02", "P02"],
        "condition": ["a", "a", "a", "a"],
        "lateral_error": [10.0, -10.0, 3.0, 5.0],
        "quadrant_error": [1.0, 0.0, np.nan, 0.0],
    })
    s = summarize(df, by=["participant_id", "condition"]).set_index(["participant_id", "metric"])
    lat = s.loc[("P01", "lateral_error")]
    assert lat["n"] == 2 and lat["mean"] == 0 and lat["median"] == 0
    assert lat["rms"] == pytest.approx(10) and lat["sd"] == pytest.approx(np.sqrt(200))
    assert bool(lat["signed"])
    q = s.loc[("P02", "quadrant_error")]
    assert q["n"] == 1 and q["mean"] == 0  # NaN (not classifiable) ignored
    assert s.loc[("P01", "quadrant_error")]["mean"] == 0.5
    assert set(s.reset_index()["metric"]) == {"lateral_error", "quadrant_error"}
