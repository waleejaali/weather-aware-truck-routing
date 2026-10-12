"""Checkpoint sampling and arrival-time estimation along a route. Pure functions.

Checkpoints are placed every `interval_miles` of route distance starting at the origin, plus the
destination. A regular checkpoint that would fall within one mile (or half an interval, if smaller)
of the destination is dropped so the destination is never duplicated by a near neighbour.
Raw geometry vertices are never used as checkpoints.

Arrival time uses constant average speed over the whole route:
    eta = departure + route.duration_s * (distance_along_route / route.distance_m)
The routing provider gives one duration per route, so per-segment speed variation (traffic, hills,
urban stretches) is not modelled; this is the main limitation of the ETA.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .geometry import path_length_m, points_at_distances
from .types import Coordinate, Route

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Checkpoint:
    index: int
    distance_m: float  # along the route, in the provider's distance scale
    fraction: float  # distance_m / route.distance_m, 0-1
    coordinate: Coordinate
    segment_m: float  # road this checkpoint stands for (half-way to each neighbour)

    @property
    def distance_miles(self) -> float:
        return self.distance_m / METERS_PER_MILE

    @property
    def segment_miles(self) -> float:
        return self.segment_m / METERS_PER_MILE


def checkpoint_distances_m(total_m: float, interval_miles: float) -> list[float]:
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")
    if total_m <= 0:
        raise ValueError("route distance must be positive")
    interval = interval_miles * METERS_PER_MILE
    min_gap = min(METERS_PER_MILE, interval / 2)
    distances = [0.0]
    k = 1
    while k * interval < total_m - min_gap:
        distances.append(k * interval)
        k += 1
    distances.append(total_m)
    return distances


def sample_checkpoints(route: Route, interval_miles: float) -> list[Checkpoint]:
    total = route.distance_m
    distances = checkpoint_distances_m(total, interval_miles)
    # The provider's distance and the geometry's haversine length differ slightly; map between them.
    scale = path_length_m(route.points) / total
    coordinates = points_at_distances(route.points, [d * scale for d in distances])
    coordinates[0], coordinates[-1] = route.points[0], route.points[-1]

    midpoints = [(a + b) / 2 for a, b in zip(distances, distances[1:])]
    starts = [0.0] + midpoints
    ends = midpoints + [total]
    return [
        Checkpoint(
            index=i,
            distance_m=distance,
            fraction=distance / total,
            coordinate=coordinate,
            segment_m=end - start,
        )
        for i, (distance, coordinate, start, end) in enumerate(zip(distances, coordinates, starts, ends))
    ]


def estimate_arrival(departure: datetime, route: Route, checkpoint: Checkpoint) -> datetime:
    """Estimated arrival (UTC) at a checkpoint. departure must be timezone-aware."""
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise ValueError("departure must be timezone-aware")
    return departure + timedelta(seconds=route.duration_s * checkpoint.fraction)
