from dataclasses import dataclass
from typing import NamedTuple


class Coordinate(NamedTuple):
    lat: float
    lon: float


@dataclass(frozen=True)
class Route:
    points: tuple[Coordinate, ...]
    distance_m: float
    duration_s: float
    strategy: str = "unspecified"  # how the planner obtained it, e.g. "baseline" or "via_waypoint"
