"""POST /api/v1/routes/assess/ - thin HTTP layer over trips.services.assess_trip.

Status codes: 200 success (including no-recommendation outcomes, which are results, not errors),
400 invalid input, 422 no drivable route, 502/503/504 routing or weather provider failure,
500 anything unexpected. Error bodies are generic; details go to the server log only.
"""

import logging
from datetime import datetime, timezone

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import error_response, flatten_errors
from routing.errors import (
    NoRouteFound,
    NoRoutesFoundError,
    ProviderAuthError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    RoutingError,
)
from routing.providers import get_routing_provider
from routing.types import Coordinate
from weather.errors import WeatherProviderError, WeatherRateLimitError, WeatherTimeoutError
from weather.providers import get_weather_provider

from .presenters import present_result
from .serializers import AssessRequestSerializer
from .services import assess_trip

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssessRoutesView(APIView):
    def post(self, request):
        data = request.data  # malformed JSON raises ParseError -> handled by core.exceptions
        serializer = AssessRequestSerializer(data=data)
        if not serializer.is_valid():
            return error_response(
                "validation_error", "The request is invalid.", 400, fields=flatten_errors(serializer.errors)
            )
        v = serializer.validated_data
        params = {
            "origin": dict(v["origin"]),
            "destination": dict(v["destination"]),
            "departure": v["departure_datetime"],
            "departure_input": data["departure_datetime"],
            "load_lb": v["load_lb"],
            "interval_miles": v["checkpoint_interval_miles"],
        }
        try:
            result = assess_trip(
                Coordinate(v["origin"]["latitude"], v["origin"]["longitude"]),
                Coordinate(v["destination"]["latitude"], v["destination"]["longitude"]),
                departure=params["departure"],
                load_lb=params["load_lb"],
                interval_miles=params["interval_miles"],
                routing_provider=get_routing_provider(),
                weather_provider=get_weather_provider(),
                now=utcnow(),
                wind_metric=settings.WEATHER_WIND_METRIC,
            )
        except RoutingError as exc:
            return _routing_failure(exc)
        except WeatherProviderError as exc:
            return _weather_failure(exc)
        except Exception:
            logger.exception("Unexpected error while assessing routes")
            return error_response("internal_error", "An unexpected error occurred.", 500)
        return Response(present_result(result, params))


def _routing_failure(exc: RoutingError) -> Response:
    logger.warning("Routing failed: %s: %s", type(exc).__name__, exc)
    if isinstance(exc, (NoRoutesFoundError, NoRouteFound)):
        return error_response("no_route_found", "No drivable route could be found between these points.", 422)
    if isinstance(exc, (ProviderConfigurationError, ProviderAuthError)):
        return error_response("routing_unavailable", "The routing service is currently unavailable.", 503)
    if isinstance(exc, ProviderRateLimitError):
        return error_response("routing_rate_limited", "The routing service is busy. Try again shortly.", 503)
    if isinstance(exc, ProviderTimeoutError):
        return error_response("routing_timeout", "The routing service did not respond in time.", 504)
    return error_response("routing_failed", "The routing service returned an error.", 502)


def _weather_failure(exc: WeatherProviderError) -> Response:
    logger.warning("Weather failed: %s: %s", type(exc).__name__, exc)
    if isinstance(exc, WeatherTimeoutError):
        return error_response("weather_timeout", "The weather service did not respond in time.", 504)
    if isinstance(exc, WeatherRateLimitError):
        return error_response("weather_rate_limited", "The weather service is busy. Try again shortly.", 503)
    return error_response("weather_failed", "The weather service returned an error.", 502)
