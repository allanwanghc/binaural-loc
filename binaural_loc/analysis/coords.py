"""Angles and coordinates, all in degrees.

vertical-polar (SOFA): azimuth 0 front, 90 left; elevation 90 up
Cartesian:             x front, y left, z up
interaural-polar:      lateral -90..90, positive left;
                       polar -90..270, 0 front, 90 up, 180 back
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

Array = NDArray[np.float64]


def wrap_angle(x: ArrayLike) -> Array:
    """Wrap to [-180, 180)."""
    return (np.asarray(x, dtype=float) + 180.0) % 360.0 - 180.0


def wrap360(x: ArrayLike) -> Array:
    """Wrap to [0, 360)."""
    return np.asarray(x, dtype=float) % 360.0


def sph_to_cart(azimuth: ArrayLike, elevation: ArrayLike) -> Array:
    """Unit vectors, shape (..., 3)."""
    az = np.deg2rad(np.asarray(azimuth, dtype=float))
    el = np.deg2rad(np.asarray(elevation, dtype=float))
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=-1)


def to_interaural_polar(azimuth: ArrayLike, elevation: ArrayLike) -> tuple[Array, Array]:
    """(lateral, polar). The polar angle is meaningless at lateral +-90."""
    v = sph_to_cart(azimuth, elevation)
    lateral = np.rad2deg(np.arcsin(np.clip(v[..., 1], -1.0, 1.0)))
    polar = np.rad2deg(np.arctan2(v[..., 2], v[..., 0]))
    polar = np.where(polar < -90.0, polar + 360.0, polar)
    return lateral, polar


def great_circle_error(az1: ArrayLike, el1: ArrayLike, az2: ArrayLike, el2: ArrayLike) -> Array:
    """Angle between two directions."""
    dot = np.sum(sph_to_cart(az1, el1) * sph_to_cart(az2, el2), axis=-1)
    return np.rad2deg(np.arccos(np.clip(dot, -1.0, 1.0)))


def mirror_front_back(azimuth: ArrayLike, elevation: ArrayLike) -> tuple[Array, Array]:
    """Reflect across the frontal plane."""
    return wrap360(180.0 - np.asarray(azimuth, dtype=float)), np.asarray(elevation, dtype=float)


def angle_from_frontal_plane(azimuth: ArrayLike, elevation: ArrayLike) -> Array:
    """Angle (0..90) between a direction and the frontal plane."""
    x = sph_to_cart(azimuth, elevation)[..., 0]
    return np.rad2deg(np.arcsin(np.clip(np.abs(x), 0.0, 1.0)))
