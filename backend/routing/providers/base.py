from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..types import Coordinate, Route


class RoutingProvider(ABC):
    name: str
    profile: str
    alternatives_max_distance_m: float | None = None  # None means no limit

    @abstractmethod
    def directions(self, waypoints: Sequence[Coordinate], *, preference: str = "recommended") -> Route:
        """preference: recommended | fastest | shortest."""

    @abstractmethod
    def alternative_routes(self, origin: Coordinate, destination: Coordinate, target_count: int) -> list[Route]:
        """May return fewer than target_count. Raises AlternativeRoutesUnavailable if unsupported for the trip."""
