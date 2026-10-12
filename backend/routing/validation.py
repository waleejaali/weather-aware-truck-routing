"""Provider-independent route validation, detour checks and de-duplication. Pure functions."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .geometry import haversine_m, overlap_fraction
from .types import Coordinate, Route


@dataclass(frozen=True)
class ValidationConfig:
    # Max distance between a route's ends and the requested origin/destination.
    endpoint_tolerance_m: float = 1500.0
    # Reject routes longer/slower than the baseline by more than this factor.
    max_detour_ratio: float = 1.5
    # Routes sharing at least this fraction of their length with an accepted route are duplicates.
    max_overlap: float = 0.9


def integrity_problems(
    route: Route, origin: Coordinate, destination: Coordinate, config: ValidationConfig
) -> list[str]:
    """Reasons the route is unusable on its own; empty list means valid."""
    problems = []
    if len(route.points) < 2:
        problems.append("geometry has fewer than 2 points")
    elif not all(_valid_point(p) for p in route.points):
        problems.append("geometry contains invalid coordinates")
    else:
        if haversine_m(route.points[0], origin) > config.endpoint_tolerance_m:
            problems.append("route does not start at the requested origin")
        if haversine_m(route.points[-1], destination) > config.endpoint_tolerance_m:
            problems.append("route does not end at the requested destination")
    for name, value in (("distance", route.distance_m), ("duration", route.duration_s)):
        if not math.isfinite(value) or value <= 0:
            problems.append(f"{name} is not a positive number")
    return problems


def rejection_reason(
    route: Route,
    accepted: Sequence[Route],
    baseline: Route | None,
    config: ValidationConfig,
) -> str | None:
    """Why an integrity-valid route should not be added to accepted, or None to accept it."""
    if baseline is not None:
        if route.distance_m > baseline.distance_m * config.max_detour_ratio:
            return f"distance is more than {config.max_detour_ratio}x the baseline route"
        if route.duration_s > baseline.duration_s * config.max_detour_ratio:
            return f"duration is more than {config.max_detour_ratio}x the baseline route"
    for other in accepted:
        shorter, longer = (route, other) if route.distance_m <= other.distance_m else (other, route)
        overlap = overlap_fraction(shorter.points, longer.points)
        if overlap >= config.max_overlap:
            return f"overlaps an accepted route by {overlap:.0%}"
    return None


def _valid_point(p: Coordinate) -> bool:
    return math.isfinite(p.lat) and math.isfinite(p.lon) and -90 <= p.lat <= 90 and -180 <= p.lon <= 180
