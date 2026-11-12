from __future__ import annotations

import math

_A = 6378137.0
_F = 1 / 298.257222101
_E2 = 2 * _F - _F * _F
_EP2 = _E2 / (1 - _E2)

_LAT0 = math.radians(38.0)
_LON0 = math.radians(127.5)
_K0 = 0.9996
_FALSE_EASTING = 1_000_000.0
_FALSE_NORTHING = 2_000_000.0

_E1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))


def _meridional_arc(latitude: float) -> float:
    return _A * (
        (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256) * latitude
        - (3 * _E2 / 8 + 3 * _E2**2 / 32 + 45 * _E2**3 / 1024) * math.sin(2 * latitude)
        + (15 * _E2**2 / 256 + 45 * _E2**3 / 1024) * math.sin(4 * latitude)
        - (35 * _E2**3 / 3072) * math.sin(6 * latitude)
    )


_M0 = _meridional_arc(_LAT0)


def utmk_to_lonlat(easting: float, northing: float) -> tuple[float, float]:
    x = easting - _FALSE_EASTING
    y = northing - _FALSE_NORTHING

    m = _M0 + y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256))
    phi1 = (
        mu
        + (3 * _E1 / 2 - 27 * _E1**3 / 32) * math.sin(2 * mu)
        + (21 * _E1**2 / 16 - 55 * _E1**4 / 32) * math.sin(4 * mu)
        + (151 * _E1**3 / 96) * math.sin(6 * mu)
        + (1097 * _E1**4 / 512) * math.sin(8 * mu)
    )

    sin_phi1, cos_phi1, tan_phi1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = _EP2 * cos_phi1**2
    t1 = tan_phi1**2
    n1 = _A / math.sqrt(1 - _E2 * sin_phi1**2)
    r1 = _A * (1 - _E2) / (1 - _E2 * sin_phi1**2) ** 1.5
    d = x / (n1 * _K0)

    latitude = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * _EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * _EP2 - 3 * c1**2) * d**6 / 720
    )
    longitude = (
        _LON0
        + (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * _EP2 + 24 * t1**2) * d**5 / 120)
        / cos_phi1
    )

    return math.degrees(longitude), math.degrees(latitude)
