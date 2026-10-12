"""Provider-agnostic weather types in normalized units (mph, inches)."""

from dataclasses import dataclass, field
from datetime import datetime

from routing.types import Coordinate


@dataclass(frozen=True)
class Attribution:
    text: str
    url: str
    license: str
    license_url: str


@dataclass(frozen=True)
class HourlyRecord:
    """One hourly weather record, stamped with its provider timestamp (UTC).

    Meaning of the timestamp T differs by field (this is how Open-Meteo defines them):
      wind_speed_mph  instantaneous value at T
      wind_gust_mph   maximum over the hour ENDING at T
      rain_in         liquid precipitation (rain + showers) summed over the hour ENDING at T
      snow_in         snowfall depth summed over the hour ENDING at T
    Because the sums cover exactly one hour, rain_in and snow_in are numerically inches per hour.
    A value is None when the provider had no data for it.
    """

    wind_speed_mph: float | None
    wind_gust_mph: float | None
    rain_in: float | None
    snow_in: float | None


@dataclass(frozen=True)
class HourlySeries:
    requested: Coordinate
    records: dict[datetime, HourlyRecord] = field(default_factory=dict)  # keys: aware UTC datetimes
    grid: Coordinate | None = None  # location the provider actually used, when it says
