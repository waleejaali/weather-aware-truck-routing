"""Assess several departure times for one trip while planning routes and fetching weather only once.

Why reuse is safe: RoutePlanner.plan() depends only on origin, destination and the routing provider's
configuration. The ORS request carries coordinates, snap radii and a preference - no departure time,
no traffic, no truck weight - so the planned geometry and duration are the same whatever the departure,
load or checkpoint interval. If routing ever starts using any of those, they MUST be added to
`route_cache_key` below and the reuse in `assess_trip_batch` must be re-examined.

Weather: checkpoint coordinates are identical for every departure (only their ETAs differ), so one
Open-Meteo fetch over the union time window serves all departures. Each departure then runs through the
unchanged `assess_routes()`: same checkpoints, ETAs, sampling, risk, coverage and ranking as the
single-departure endpoint.
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import BaseCache, caches

from routing.checkpoints import sample_checkpoints
from routing.providers.base import RoutingProvider
from routing.services.route_planner import PlannerConfig, RoutePlan, RoutePlanner
from routing.types import Coordinate
from weather.errors import WeatherProviderError
from weather.providers.base import WeatherProvider
from weather.sampling import ceil_hour, floor_hour
from weather.types import HourlySeries

from .assessment import TripAssessment, assess_routes

logger = logging.getLogger(__name__)
_HOUR = timedelta(hours=1)


# -- planned-route cache --------------------------------------------------------------------------


def route_cache_key(origin: Coordinate, destination: Coordinate, provider: RoutingProvider, config: PlannerConfig) -> str:
    """Everything the planned routes depend on. Deliberately excludes departure, load and checkpoint interval."""
    payload = {
        "origin": [round(origin.lat, 6), round(origin.lon, 6)],
        "destination": [round(destination.lat, 6), round(destination.lon, 6)],
        "provider": provider.name,
        "profile": provider.profile,
        "planner": repr(config),
    }
    return "route-plan:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _request_count(provider: object) -> int | None:
    count = getattr(provider, "request_count", None)
    return count if isinstance(count, int) else None


def plan_routes_cached(
    origin: Coordinate,
    destination: Coordinate,
    provider: RoutingProvider,
    config: PlannerConfig | None = None,
    *,
    cache: BaseCache | None = None,
    ttl: int | None = None,
) -> tuple[RoutePlan, bool, int | None]:
    """Plan routes, reusing a recent identical plan. Returns (plan, cache_hit, routing_http_requests).

    Only successful plans are cached; provider failures propagate and are never stored. A broken cache
    backend degrades to planning every time rather than failing the request.
    """
    config = config or PlannerConfig()
    ttl = settings.ROUTE_CACHE_TTL_SECONDS if ttl is None else ttl
    cache = cache if cache is not None else caches["routes"]
    key = route_cache_key(origin, destination, provider, config)

    if ttl > 0:
        try:
            cached = cache.get(key)
        except Exception:  # noqa: BLE001 - cache problems must never break an assessment
            logger.warning("Route cache read failed; planning without it", exc_info=True)
            cached = None
        if isinstance(cached, RoutePlan):
            return cached, True, 0

    before = _request_count(provider)
    plan = RoutePlanner(provider, config).plan(origin, destination)
    after = _request_count(provider)
    if ttl > 0:
        try:
            cache.set(key, plan, ttl)
        except Exception:  # noqa: BLE001
            logger.warning("Route cache write failed; continuing uncached", exc_info=True)
    return plan, False, (after - before) if before is not None and after is not None else None


# -- shared weather fetch -------------------------------------------------------------------------


class PrimedWeatherProvider(WeatherProvider):
    """Wraps a weather provider so one up-front fetch can serve many `assess_routes` calls.

    `prime()` fetches hourly data for a set of locations over a time window. `fetch_hourly()` then answers
    from that data when every requested location is primed and the requested window lies inside the primed
    one; otherwise it delegates to the wrapped provider (so nothing is ever guessed or substituted).
    """

    def __init__(self, inner: WeatherProvider):
        self._inner = inner
        self.name = inner.name
        self.attribution = inner.attribution
        self._series: dict[Coordinate, HourlySeries] = {}
        self._window: tuple[datetime, datetime] | None = None
        self.fallback_fetches = 0

    @property
    def inner(self) -> WeatherProvider:
        return self._inner

    def available_window(self, now: datetime) -> tuple[datetime, datetime]:
        return self._inner.available_window(now)

    def prime(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> None:
        series = self._inner.fetch_hourly(locations, start, end)
        self._series = {location: s for location, s in zip(locations, series)}
        self._window = (start, end)

    def fetch_hourly(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> list[HourlySeries]:
        if self._window and start >= self._window[0] and end <= self._window[1] and all(l in self._series for l in locations):
            return [HourlySeries(requested=l, records=self._series[l].records, grid=self._series[l].grid) for l in locations]
        self.fallback_fetches += 1
        return self._inner.fetch_hourly(locations, start, end)


def _prime_weather(
    primed: PrimedWeatherProvider,
    plan: RoutePlan,
    departures: Sequence[datetime],
    interval_miles: float,
    now: datetime,
) -> None:
    """One weather fetch covering every checkpoint of every route across every departure's time span."""
    window_start, window_end = primed.available_window(now)
    last_servable_hour = window_end - _HOUR
    locations: list[Coordinate] = []
    seen: set[Coordinate] = set()
    lo: datetime | None = None
    hi: datetime | None = None
    for route in plan.routes:
        for checkpoint in sample_checkpoints(route, interval_miles):
            if checkpoint.coordinate not in seen:
                seen.add(checkpoint.coordinate)
                locations.append(checkpoint.coordinate)
        for departure in departures:
            start = max(floor_hour(departure), window_start)
            end = min(ceil_hour(departure + timedelta(seconds=route.duration_s)), last_servable_hour)
            if start <= end:
                lo = start if lo is None else min(lo, start)
                hi = end if hi is None else max(hi, end)
    if locations and lo is not None and hi is not None:
        primed.prime(locations, lo, hi)


# -- the batch ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DepartureOutcome:
    departure: datetime  # UTC
    departure_input: str  # as sent by the client
    assessment: TripAssessment | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class BatchResult:
    plan: RoutePlan
    outcomes: tuple[DepartureOutcome, ...]
    weather_provider_name: str
    route_cache_hit: bool
    routing_requests: int | None  # HTTP requests to the routing provider made by this call (0 on a cache hit)
    weather_requests: int | None
    generated_at: datetime


def assess_trip_batch(
    origin: Coordinate,
    destination: Coordinate,
    *,
    departures: Sequence[datetime],
    departure_inputs: Sequence[str],
    load_lb: float,
    interval_miles: float,
    routing_provider: RoutingProvider,
    weather_provider: WeatherProvider,
    now: datetime,
    wind_metric: str = "sustained",
    planner_config: PlannerConfig | None = None,
    route_cache: BaseCache | None = None,
    route_cache_ttl: int | None = None,
) -> BatchResult:
    """Assess the same trip at several departures. Routing and weather failures that affect every departure
    raise (as in the single endpoint); a failure confined to one departure is reported on that departure only."""
    plan, cache_hit, routing_requests = plan_routes_cached(
        origin, destination, routing_provider, planner_config, cache=route_cache, ttl=route_cache_ttl
    )

    weather_before = _request_count(weather_provider)
    primed = PrimedWeatherProvider(weather_provider)
    _prime_weather(primed, plan, [d.astimezone(timezone.utc) for d in departures], interval_miles, now)

    outcomes: list[DepartureOutcome] = []
    for departure, text in zip(departures, departure_inputs):
        utc = departure.astimezone(timezone.utc)
        try:
            assessment = assess_routes(
                plan.routes,
                departure=utc,
                load_lb=load_lb,
                interval_miles=interval_miles,
                provider=primed,
                now=now,
                wind_metric=wind_metric,
            )
            outcomes.append(DepartureOutcome(utc, text, assessment))
        except WeatherProviderError as exc:
            logger.warning("Weather failed for one departure: %s: %s", type(exc).__name__, exc)
            outcomes.append(DepartureOutcome(utc, text, None, "weather_failed", "Weather could not be fetched for this departure."))
        except Exception:  # noqa: BLE001 - isolate a bad departure from the rest of the batch
            logger.exception("Unexpected error assessing one departure")
            outcomes.append(DepartureOutcome(utc, text, None, "assessment_failed", "This departure could not be assessed."))

    weather_after = _request_count(weather_provider)
    return BatchResult(
        plan=plan,
        outcomes=tuple(outcomes),
        weather_provider_name=weather_provider.name,
        route_cache_hit=cache_hit,
        routing_requests=routing_requests,
        weather_requests=(weather_after - weather_before) if weather_before is not None and weather_after is not None else None,
        generated_at=now.astimezone(timezone.utc),
    )
