"""Provider-agnostic routing types."""

from dataclasses import dataclass
from typing import NamedTuple


class Coordinate(NamedTuple):
    lat: float
    lon: float


@dataclass(frozen=True)
class Route:
    """A drivable route between two places, as returned by a routing provider."""

    points: tuple[Coordinate, ...]
    distance_m: float
    duration_s: float
    # How the route was obtained, e.g. "provider_alternative", "baseline", "via_waypoint".
    strategy: str = "unspecified"
