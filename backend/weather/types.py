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
    # Wind speed is instantaneous at the timestamp; gust, rain and snow cover the hour ending at it,
    # so rain_in and snow_in are effectively inches per hour.
    wind_speed_mph: float | None
    wind_gust_mph: float | None
    rain_in: float | None  # rain + showers
    snow_in: float | None


@dataclass(frozen=True)
class HourlySeries:
    requested: Coordinate
    records: dict[datetime, HourlyRecord] = field(default_factory=dict)  # keyed by aware UTC hour
    grid: Coordinate | None = None  # model grid point the provider snapped to, if reported
