"""The routing + weather + risk pipeline as one callable, shared by the API and management commands."""

from dataclasses import dataclass
from datetime import datetime

from routing.providers.base import RoutingProvider
from routing.services.route_planner import PlannerConfig, RoutePlan, RoutePlanner
from routing.types import Coordinate
from weather.providers.base import WeatherProvider

from .assessment import TripAssessment, assess_routes


@dataclass(frozen=True)
class TripResult:
    plan: RoutePlan
    assessment: TripAssessment
    weather_provider_name: str


def assess_trip(
    origin: Coordinate,
    destination: Coordinate,
    *,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    routing_provider: RoutingProvider,
    weather_provider: WeatherProvider,
    now: datetime,
    wind_metric: str = "sustained",
    planner_config: PlannerConfig | None = None,
) -> TripResult:
    """Plan up to three routes, then assess weather risk along each and rank them.

    Raises routing.errors.RoutingError or weather.errors.WeatherProviderError on provider failure.
    """
    plan = RoutePlanner(routing_provider, planner_config).plan(origin, destination)
    assessment = assess_routes(
        plan.routes,
        departure=departure,
        load_lb=load_lb,
        interval_miles=interval_miles,
        provider=weather_provider,
        now=now,
        wind_metric=wind_metric,
    )
    return TripResult(plan, assessment, weather_provider.name)
