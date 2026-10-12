"""Pure geometry helpers on (lat, lon) paths. No network or Django imports."""

import math
from collections.abc import Sequence

from .types import Coordinate

EARTH_RADIUS_M = 6_371_008.8
_GRID_CELL_DEG = 0.02  # ~2 km; assumes mid-latitude (US) routes


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def initial_bearing_deg(a: Coordinate, b: Coordinate) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlon = math.radians(b.lon - a.lon)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def destination_point(origin: Coordinate, bearing_deg: float, distance_m: float) -> Coordinate:
    """Point reached travelling distance_m from origin along a great circle."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    lat1, lon1 = math.radians(origin.lat), math.radians(origin.lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta))
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return Coordinate(math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def path_length_m(points: Sequence[Coordinate]) -> float:
    return sum(haversine_m(a, b) for a, b in zip(points, points[1:]))


def _cumulative_m(points: Sequence[Coordinate]) -> list[float]:
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine_m(a, b))
    return cumulative


def _locate(points: Sequence[Coordinate], cumulative: Sequence[float], distance_m: float) -> Coordinate:
    distance_m = max(0.0, min(distance_m, cumulative[-1]))
    for i in range(1, len(points)):
        if cumulative[i] >= distance_m:
            segment = cumulative[i] - cumulative[i - 1]
            t = 0.0 if segment == 0 else (distance_m - cumulative[i - 1]) / segment
            a, b = points[i - 1], points[i]
            return Coordinate(a.lat + (b.lat - a.lat) * t, a.lon + (b.lon - a.lon) * t)
    return points[-1]


def point_and_bearing_at_fraction(points: Sequence[Coordinate], fraction: float) -> tuple[Coordinate, float]:
    """Point at a fraction of the path length, and the local travel bearing there."""
    cumulative = _cumulative_m(points)
    total = cumulative[-1]
    here = _locate(points, cumulative, fraction * total)
    before = _locate(points, cumulative, (fraction - 0.02) * total)
    after = _locate(points, cumulative, (fraction + 0.02) * total)
    return here, initial_bearing_deg(before, after)


def resample(points: Sequence[Coordinate], step_m: float) -> list[Coordinate]:
    """Points spaced step_m apart along the path (plus the final point)."""
    cumulative = _cumulative_m(points)
    total = cumulative[-1]
    if total == 0:
        return [points[0]]
    result = []
    index = 1
    distance = 0.0
    while distance < total:
        # Walk forward through segments instead of rescanning from the start.
        while cumulative[index] < distance:
            index += 1
        segment = cumulative[index] - cumulative[index - 1]
        t = 0.0 if segment == 0 else (distance - cumulative[index - 1]) / segment
        a, b = points[index - 1], points[index]
        result.append(Coordinate(a.lat + (b.lat - a.lat) * t, a.lon + (b.lon - a.lon) * t))
        distance += step_m
    result.append(points[-1])
    return result


def overlap_fraction(
    candidate: Sequence[Coordinate],
    other: Sequence[Coordinate],
    *,
    tolerance_m: float = 500.0,
    sample_step_m: float = 500.0,
) -> float:
    """Share (0-1) of candidate's length that runs within tolerance_m of other."""
    samples = resample(candidate, sample_step_m)
    grid: dict[tuple[int, int], list[Coordinate]] = {}
    for p in resample(other, tolerance_m / 2):
        grid.setdefault(_cell(p), []).append(p)

    def near(p: Coordinate) -> bool:
        ci, cj = _cell(p)
        return any(
            haversine_m(p, q) <= tolerance_m
            for di in (-1, 0, 1)
            for dj in (-1, 0, 1)
            for q in grid.get((ci + di, cj + dj), ())
        )

    return sum(1 for p in samples if near(p)) / len(samples)


def _cell(p: Coordinate) -> tuple[int, int]:
    return math.floor(p.lat / _GRID_CELL_DEG), math.floor(p.lon / _GRID_CELL_DEG)
