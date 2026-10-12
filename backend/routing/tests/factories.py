"""Synthetic test fixtures. These are NOT real routes; they only exercise the logic."""

import math
from collections.abc import Sequence

from routing.geometry import path_length_m
from routing.types import Coordinate, Route

LOS_ANGELES = Coordinate(34.0522, -118.2437)
DALLAS = Coordinate(32.7767, -96.7970)
SAN_DIEGO = Coordinate(32.7157, -117.1611)
NEAR_LOS_ANGELES = Coordinate(34.2, -118.0)  # ~25 km from LOS_ANGELES, well within 100 km
AVERAGE_SPEED_MS = 25.0


def line_points(a: Coordinate, b: Coordinate, *, bulge_deg: float = 0.0, n: int = 80) -> list[Coordinate]:
    """Straight line from a to b, optionally bowed sideways (in latitude degrees)."""
    return [
        Coordinate(
            a.lat + (b.lat - a.lat) * t + bulge_deg * math.sin(math.pi * t),
            a.lon + (b.lon - a.lon) * t,
        )
        for t in (i / (n - 1) for i in range(n))
    ]


def route_from_points(points: Sequence[Coordinate], strategy: str = "provider") -> Route:
    distance = path_length_m(points)
    return Route(tuple(points), distance, distance / AVERAGE_SPEED_MS, strategy)


def make_route(a: Coordinate, b: Coordinate, bulge_deg: float = 0.0) -> Route:
    return route_from_points(line_points(a, b, bulge_deg=bulge_deg))


def route_via(a: Coordinate, via: Coordinate, b: Coordinate) -> Route:
    points = line_points(a, via, n=40) + line_points(via, b, n=40)[1:]
    return route_from_points(points)
