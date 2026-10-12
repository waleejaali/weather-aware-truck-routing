"""Open-Meteo adapter (https://open-meteo.com/en/docs). All Open-Meteo knowledge lives here.

Variables (hourly): wind_speed_10m (instant), wind_gusts_10m (max of preceding hour), rain and
showers (liquid, sum of preceding hour), snowfall (snow depth, sum of preceding hour).
Requested in mph and inches; with precipitation_unit=inch, snowfall is converted from cm to inch
(verified against the live API). `precipitation` is NOT used: it includes snow water equivalent.

Free API terms: non-commercial use, CC BY 4.0 attribution (see `attribution`), fewer than 10,000
calls/day. Data is served for roughly 92 days back to 16 days ahead.
"""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from routing.types import Coordinate

from ..errors import (
    WeatherConnectionError,
    WeatherRateLimitError,
    WeatherRequestError,
    WeatherResponseError,
    WeatherTimeoutError,
)
from ..types import Attribution, HourlyRecord, HourlySeries
from .base import WeatherProvider

HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
# Open-Meteo reports mph as "mp/h". Every response is checked so a silent unit change cannot
# turn kilometres/hour or centimetres into risk inputs.
_EXPECTED_UNITS = {
    "wind_speed_10m": {"mp/h", "mph"},
    "wind_gusts_10m": {"mp/h", "mph"},
    "rain": {"inch"},
    "showers": {"inch"},
    "snowfall": {"inch"},
}
MAX_LOCATIONS_PER_REQUEST = 50
PAST_DAYS_AVAILABLE = 92
FORECAST_DAYS_AVAILABLE = 16
_DEDUPE_DECIMALS = 2  # ~1.1 km, finer than the weather model grid


class OpenMeteoProvider(WeatherProvider):
    name = "open-meteo"
    attribution = Attribution(
        text="Weather data by Open-Meteo.com",
        url="https://open-meteo.com/",
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    )

    def __init__(
        self,
        *,
        base_url: str = "https://api.open-meteo.com",
        timeout_s: float = 20.0,
        max_locations_per_request: int = MAX_LOCATIONS_PER_REQUEST,
        session: requests.Session | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_locations = max_locations_per_request
        self._session = session or requests.Session()

    def available_window(self, now: datetime) -> tuple[datetime, datetime]:
        today = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=PAST_DAYS_AVAILABLE), today + timedelta(days=FORECAST_DAYS_AVAILABLE)

    def fetch_hourly(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> list[HourlySeries]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if end < start:
            raise ValueError("end must not be before start")
        start_date = start.astimezone(timezone.utc).date().isoformat()
        end_date = end.astimezone(timezone.utc).date().isoformat()

        # One request per chunk of unique (rounded) locations, not one per checkpoint.
        unique: dict[tuple[float, float], Coordinate] = {}
        for location in locations:
            unique.setdefault(_key(location), location)
        keys = list(unique)
        by_key: dict[tuple[float, float], HourlySeries] = {}
        for i in range(0, len(keys), self._max_locations):
            chunk = [unique[k] for k in keys[i : i + self._max_locations]]
            for k, series in zip(keys[i : i + self._max_locations], self._fetch_chunk(chunk, start_date, end_date)):
                by_key[k] = series
        return [
            HourlySeries(requested=location, records=by_key[_key(location)].records, grid=by_key[_key(location)].grid)
            for location in locations
        ]

    # -- request -----------------------------------------------------------------------------

    def _fetch_chunk(self, chunk: Sequence[Coordinate], start_date: str, end_date: str) -> list[HourlySeries]:
        params = {
            "latitude": ",".join(f"{c.lat:.4f}" for c in chunk),
            "longitude": ",".join(f"{c.lon:.4f}" for c in chunk),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",  # unambiguous UTC epoch seconds
            "timezone": "GMT",
            "start_date": start_date,
            "end_date": end_date,
        }
        try:
            response = self._session.get(f"{self._base_url}/v1/forecast", params=params, timeout=self._timeout_s)
        except requests.Timeout as exc:
            raise WeatherTimeoutError(f"Open-Meteo did not respond within {self._timeout_s:g}s") from exc
        except requests.ConnectionError as exc:
            raise WeatherConnectionError("Could not connect to Open-Meteo") from exc
        except requests.RequestException as exc:
            raise WeatherConnectionError(f"Open-Meteo request failed: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise WeatherRateLimitError("Open-Meteo rate limit exceeded")
        if response.status_code != 200:
            raise WeatherRequestError(
                f"Open-Meteo HTTP {response.status_code}: {_reason(response)}", status_code=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherResponseError("Open-Meteo returned a non-JSON response") from exc

        # One location returns an object; several return a list.
        entries = payload if isinstance(payload, list) else [payload]
        if len(entries) != len(chunk):
            raise WeatherResponseError(f"Open-Meteo returned {len(entries)} locations for {len(chunk)} requested")
        return [self._parse_location(location, entry) for location, entry in zip(chunk, entries)]

    # -- response ----------------------------------------------------------------------------

    def _parse_location(self, requested: Coordinate, entry: Any) -> HourlySeries:
        try:
            hourly, units = entry["hourly"], entry["hourly_units"]
            times = hourly["time"]
            columns = {name: hourly[name] for name in HOURLY_VARIABLES}
        except (KeyError, TypeError) as exc:
            raise WeatherResponseError(f"Open-Meteo payload is missing expected fields: {exc}") from exc

        for name, accepted in _EXPECTED_UNITS.items():
            if units.get(name) not in accepted:
                raise WeatherResponseError(f"Unexpected unit for {name}: {units.get(name)!r}")
        if not isinstance(times, list) or any(not isinstance(c, list) or len(c) != len(times) for c in columns.values()):
            raise WeatherResponseError("Open-Meteo hourly arrays have inconsistent lengths")

        records: dict[datetime, HourlyRecord] = {}
        for i, stamp in enumerate(times):
            if isinstance(stamp, bool) or not isinstance(stamp, int):
                raise WeatherResponseError(f"Unexpected timestamp {stamp!r}")
            rain, showers = _number(columns["rain"][i]), _number(columns["showers"][i])
            records[datetime.fromtimestamp(stamp, tz=timezone.utc)] = HourlyRecord(
                wind_speed_mph=_number(columns["wind_speed_10m"][i]),
                wind_gust_mph=_number(columns["wind_gusts_10m"][i]),
                # Liquid precipitation needs both parts; a missing part is not assumed to be zero.
                rain_in=None if rain is None or showers is None else rain + showers,
                snow_in=_number(columns["snowfall"][i]),
            )
        grid = None
        if isinstance(entry.get("latitude"), (int, float)) and isinstance(entry.get("longitude"), (int, float)):
            grid = Coordinate(float(entry["latitude"]), float(entry["longitude"]))
        return HourlySeries(requested=requested, records=records, grid=grid)


def _key(c: Coordinate) -> tuple[float, float]:
    return round(c.lat, _DEDUPE_DECIMALS), round(c.lon, _DEDUPE_DECIMALS)


def _number(value: Any) -> float | None:
    """A finite number, or None for JSON null. Anything else is a malformed payload."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherResponseError(f"Unexpected weather value {value!r}")
    if not math.isfinite(value):
        return None
    return float(value)


def _reason(response: requests.Response) -> str:
    try:
        return str(response.json().get("reason", "no reason given"))[:300]
    except (ValueError, AttributeError):
        return "no reason given"
