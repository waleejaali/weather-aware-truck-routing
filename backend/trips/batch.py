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


def route_cache_key(origin: Coordinate, destination: Coordinate, provider: RoutingProvider, config: PlannerConfig) -> str:
    # ORS requests don't use departure time, traffic or weight, so those are deliberately left out.
    # If routing ever starts depending on them, they must be added here.
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
    """Returns (plan, cache_hit, routing_http_requests)."""
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


class PrimedWeatherProvider(WeatherProvider):
    """Serves fetch_hourly from one up-front fetch; falls through to the real provider on any miss."""

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
    # Checkpoint coordinates don't depend on departure, so one fetch over the union window covers all of them.
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


@dataclass(frozen=True)
class DepartureOutcome:
    departure: datetime  # UTC
    departure_input: str
    assessment: TripAssessment | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class BatchResult:
    plan: RoutePlan
    outcomes: tuple[DepartureOutcome, ...]
    weather_provider_name: str
    route_cache_hit: bool
    routing_requests: int | None
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
