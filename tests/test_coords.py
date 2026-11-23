from __future__ import annotations

import numpy as np
import pytest

from binaural_loc.analysis.coords import (
    angle_from_frontal_plane,
    great_circle_error,
    mirror_front_back,
    sph_to_cart,
    to_interaural_polar,
    wrap360,
    wrap_angle,
)


@pytest.mark.parametrize(
    "x, expected",
    [(0, 0), (359, -1), (1, 1), (180, -180), (-180, -180), (179.5, 179.5), (540, -180), (-190, 170)],
)
def test_wrap_angle(x, expected):
    assert wrap_angle(x) == pytest.approx(expected)


def test_wrap_angle_differences():
    # the difference between 359 and 1 is 2 degrees, in either direction
    assert wrap_angle(1 - 359) == pytest.approx(2)
    assert wrap_angle(359 - 1) == pytest.approx(-2)


def test_wrap360():
    assert list(wrap360([-90, 0, 360, 725])) == [270, 0, 0, 5]


def test_sph_to_cart_axes():
    np.testing.assert_allclose(sph_to_cart(0, 0), [1, 0, 0], atol=1e-12)    # front = +x
    np.testing.assert_allclose(sph_to_cart(90, 0), [0, 1, 0], atol=1e-12)   # left = +y
    np.testing.assert_allclose(sph_to_cart(0, 90), [0, 0, 1], atol=1e-12)   # up = +z
    np.testing.assert_allclose(sph_to_cart(270, 0), [0, -1, 0], atol=1e-12)


@pytest.mark.parametrize(
    "az, el, lat, pol",
    [
        (0, 0, 0, 0),
        (180, 0, 0, 180),
        (0, 90, 0, 90),
        (0, -90, 0, -90),
        (180, -45, 0, 225),      # back-down: polar in [-90, 270)
        (180, 45, 0, 135),
        (45, 0, 45, 0),          # front-left on the horizontal plane
        (135, 0, 45, 180),       # back-left: same lateral, polar 180
        (315, 0, -45, 0),        # front-right
        (30, 30, np.rad2deg(np.arcsin(np.cos(np.pi / 6) * 0.5)), np.rad2deg(np.arctan2(0.5, 0.75))),
    ],
)
def test_interaural_polar_known_values(az, el, lat, pol):
    la, po = to_interaural_polar(az, el)
    assert la == pytest.approx(lat, abs=1e-9)
    assert po == pytest.approx(pol, abs=1e-9)


def test_interaural_polar_reconstructs_direction():
    rng = np.random.default_rng(1)
    az, el = rng.uniform(0, 360, 1000), rng.uniform(-90, 90, 1000)
    lat, pol = np.deg2rad(to_interaural_polar(az, el))
    v = np.stack([np.cos(lat) * np.cos(pol), np.sin(lat), np.cos(lat) * np.sin(pol)], axis=-1)
    np.testing.assert_allclose(v, sph_to_cart(az, el), atol=1e-9)
    assert np.all((pol >= -np.pi / 2) & (pol < 3 * np.pi / 2))


def test_great_circle_error():
    assert great_circle_error(0, 0, 0, 0) == pytest.approx(0)
    assert great_circle_error(0, 0, 180, 0) == pytest.approx(180)
    assert great_circle_error(0, 0, 90, 0) == pytest.approx(90)
    assert great_circle_error(10, 0, 350, 0) == pytest.approx(20)
    assert great_circle_error(0, 90, 123, 90) == pytest.approx(0, abs=1e-6)  # azimuth irrelevant at the pole
    # identical directions must not give NaN from rounding (dot slightly > 1)
    rng = np.random.default_rng(2)
    az, el = rng.uniform(0, 360, 1000), rng.uniform(-90, 90, 1000)
    e = great_circle_error(az, el, az, el)
    assert not np.isnan(e).any() and np.all(e < 1e-5)


def test_mirror_front_back():
    az, el = mirror_front_back([0, 30, 90, 300], [10, 10, 10, 10])
    np.testing.assert_allclose(az, [180, 150, 90, 240])
    np.testing.assert_allclose(el, 10)


def test_angle_from_frontal_plane():
    np.testing.assert_allclose(angle_from_frontal_plane([0, 180, 90, 270, 45, 0], [0, 0, 0, 0, 0, 90]),
                               [90, 90, 0, 0, 45, 0], atol=1e-9)
