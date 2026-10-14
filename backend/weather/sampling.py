from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .types import HourlyRecord, HourlySeries

_HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class SampledConditions:
    wind_mph: float | None
    gust_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None
    missing: tuple[str, ...]  # subset of: wind, gust, rain, snow


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def ceil_hour(t: datetime) -> datetime:
    f = floor_hour(t)
    return f if f == t.astimezone(timezone.utc) else f + _HOUR


def sample_conditions(series: HourlySeries, arrival: datetime) -> SampledConditions:
    if arrival.tzinfo is None:
        raise ValueError("arrival must be timezone-aware")
    t = arrival.astimezone(timezone.utc)
    lower, upper = floor_hour(t), ceil_hour(t)
    upper_record = series.records.get(upper)

    # Wind speed is instantaneous, so interpolate. Gust/rain/snow cover the preceding hour,
    # so the record stamped ceil(t) is the one whose window contains t.
    wind = _interpolated_wind(series.records.get(lower), upper_record, lower, t)
    gust = _field(upper_record, "wind_gust_mph")
    rain = _field(upper_record, "rain_in")
    snow = _field(upper_record, "snow_in")
    missing = tuple(
        name for name, value in (("wind", wind), ("gust", gust), ("rain", rain), ("snow", snow)) if value is None
    )
    return SampledConditions(wind, gust, rain, snow, missing)


def _field(record: HourlyRecord | None, name: str) -> float | None:
    return None if record is None else getattr(record, name)


def _interpolated_wind(
    lower: HourlyRecord | None, upper: HourlyRecord | None, lower_time: datetime, t: datetime
) -> float | None:
    lo = _field(lower, "wind_speed_mph")
    if t == lower_time:
        return lo
    hi = _field(upper, "wind_speed_mph")
    if lo is None or hi is None:
        return None
    weight = (t - lower_time) / _HOUR
    return lo + (hi - lo) * weight
