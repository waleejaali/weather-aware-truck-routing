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
        """[start, end) of hours the provider can serve right now, in UTC."""

    @abstractmethod
    def fetch_hourly(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> list[HourlySeries]:
        """One series per location, same order. Missing hours are left out, never filled in."""
