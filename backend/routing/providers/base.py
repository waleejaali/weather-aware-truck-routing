"""Interface every routing provider adapter implements."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..types import Coordinate, Route


class RoutingProvider(ABC):
    name: str
    # Vehicle profile actually used for requests. Reported to callers, never swapped silently.
    profile: str
    # Longest origin-destination distance for provider-computed alternatives; None if unlimited.
    alternatives_max_distance_m: float | None = None

    @abstractmethod
    def directions(self, waypoints: Sequence[Coordinate], *, preference: str = "recommended") -> Route:
        """One route through the waypoints in order. preference: recommended | fastest | shortest."""

    @abstractmethod
    def alternative_routes(self, origin: Coordinate, destination: Coordinate, target_count: int) -> list[Route]:
        """Provider-computed alternatives (may return fewer than target_count).

        Raises AlternativeRoutesUnavailable if the provider cannot do this for the request.
        """
