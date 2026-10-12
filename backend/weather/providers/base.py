"""Interface every weather provider adapter implements."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from routing.types import Coordinate

from ..types import Attribution, HourlySeries


class WeatherProvider(ABC):
    name: str
    attribution: Attribution

    @abstractmethod
    def available_window(self, now: datetime) -> tuple[datetime, datetime]:
        """[start, end) of hours the provider can currently serve (aware UTC)."""

    @abstractmethod
    def fetch_hourly(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> list[HourlySeries]:
        """Hourly records covering [start, end] for every location, in the same order as locations.

        Must batch requests where the API allows. Hours the provider has no data for are simply
        absent (or have None fields); nothing is substituted. Raises WeatherProviderError subclasses.
        """
