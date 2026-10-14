"""OpenRouteService (ORS) adapter. All ORS-specific request/response knowledge lives here.

Endpoint: POST {base}/v2/directions/{profile}/geojson, key sent in the Authorization header
(never in the URL, so it cannot leak into logs). Documented hosted-API limits:
https://openrouteservice.org/restrictions/ (alternative routes: <= 100 km, <= 3 routes).
"""

import math
from collections.abc import Sequence
from typing import Any

import requests

from ..errors import (
    AlternativeRoutesUnavailable,
    NoRouteFound,
    ProviderAuthError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from ..types import Coordinate, Route
from .base import RoutingProvider

MAX_WAYPOINTS = 50  # documented hosted limit
ENDPOINT_SNAP_RADIUS_M = 1000  # how far origin/destination may snap to the nearest road
VIA_SNAP_RADIUS_M = 20_000  # intermediate points are synthetic, so allow a wider search
ALTERNATIVE_WEIGHT_FACTOR = 1.4  # ORS default: alternatives up to 1.4x the optimal cost
ALTERNATIVE_SHARE_FACTOR = 0.6  # ORS default: alternatives share up to 60% with the optimal route

# ORS error codes (see ORS error code documentation); confirmed only via live testing.
_CODE_PARAMETERS_EXCEED_LIMITS = 2004
_CODES_NO_ROUTE = {2009, 2010}


class OpenRouteServiceProvider(RoutingProvider):
    name = "openrouteservice"
    alternatives_max_distance_m = 100_000.0

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openrouteservice.org",
        profile: str = "driving-hgv",
        timeout_s: float = 30.0,
        session: requests.Session | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.profile = profile
        self._timeout_s = timeout_s
        self._session = session or requests.Session()
        self.request_count = 0  # HTTP requests sent by this instance

    def directions(self, waypoints: Sequence[Coordinate], *, preference: str = "recommended") -> Route:
        body = self._body(waypoints)
        body["preference"] = preference
        routes = self._parse_routes(self._post(body))
        if not routes:
            raise ProviderResponseError("ORS returned no routes")
        return routes[0]

    def alternative_routes(self, origin: Coordinate, destination: Coordinate, target_count: int) -> list[Route]:
        body = self._body([origin, destination])
        body["alternative_routes"] = {
            "target_count": target_count,
            "weight_factor": ALTERNATIVE_WEIGHT_FACTOR,
            "share_factor": ALTERNATIVE_SHARE_FACTOR,
        }
        return self._parse_routes(self._post(body, alternatives=True))

    # -- request -----------------------------------------------------------------------------

    def _body(self, waypoints: Sequence[Coordinate]) -> dict[str, Any]:
        if not 2 <= len(waypoints) <= MAX_WAYPOINTS:
            raise ValueError(f"ORS needs between 2 and {MAX_WAYPOINTS} waypoints, got {len(waypoints)}")
        radiuses = [ENDPOINT_SNAP_RADIUS_M] + [VIA_SNAP_RADIUS_M] * (len(waypoints) - 2) + [ENDPOINT_SNAP_RADIUS_M]
        return {
            # ORS expects [longitude, latitude].
            "coordinates": [[p.lon, p.lat] for p in waypoints],
            "radiuses": radiuses,
            "instructions": False,
        }

    def _post(self, body: dict[str, Any], *, alternatives: bool = False) -> dict[str, Any]:
        if not self._api_key:
            raise ProviderConfigurationError(
                "ORS_API_KEY is not set. Add it to the .env file at the repository root "
                "(see .env.example); get a free key at https://openrouteservice.org/dev/#/signup."
            )
        url = f"{self._base_url}/v2/directions/{self.profile}/geojson"
        headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/geo+json, application/json",
        }
        self.request_count += 1
        try:
            response = self._session.post(url, json=body, headers=headers, timeout=self._timeout_s)
        except requests.Timeout as exc:
            raise ProviderTimeoutError(f"ORS did not respond within {self._timeout_s:g}s") from exc
        except requests.ConnectionError as exc:
            raise ProviderConnectionError("Could not connect to ORS") from exc
        except requests.RequestException as exc:
            raise ProviderConnectionError(f"ORS request failed: {type(exc).__name__}") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderResponseError("ORS returned a non-JSON response") from exc
            if not isinstance(payload, dict):
                raise ProviderResponseError("ORS returned an unexpected JSON structure")
            return payload
        raise self._error_for(response, alternatives=alternatives)

    def _error_for(self, response: requests.Response, *, alternatives: bool) -> Exception:
        status = response.status_code
        code, message = _error_details(response)
        detail = f"ORS HTTP {status}" + (f" (code {code})" if code is not None else "") + f": {message}"
        if status in (401, 403):
            return ProviderAuthError(f"ORS rejected the API key. {detail}")
        if status == 429:
            return ProviderRateLimitError(f"ORS rate limit or quota exceeded. {detail}")
        if status in (400, 404) and code in _CODES_NO_ROUTE:
            return NoRouteFound(detail, status_code=status, code=code)
        if alternatives and status == 400 and code == _CODE_PARAMETERS_EXCEED_LIMITS:
            return AlternativeRoutesUnavailable(detail, status_code=status, code=code)
        return ProviderRequestError(detail, status_code=status, code=code)

    # -- response ----------------------------------------------------------------------------

    def _parse_routes(self, payload: dict[str, Any]) -> list[Route]:
        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderResponseError("ORS response has no 'features' list")
        return [self._parse_feature(f) for f in features]

    def _parse_feature(self, feature: Any) -> Route:
        try:
            coordinates = feature["geometry"]["coordinates"]
            summary = feature["properties"]["summary"]
            distance, duration = summary["distance"], summary["duration"]
            if feature["geometry"]["type"] != "LineString":
                raise ValueError("geometry is not a LineString")
            points = tuple(Coordinate(float(c[1]), float(c[0])) for c in coordinates)
            if isinstance(distance, bool) or isinstance(duration, bool):
                raise ValueError("summary values must be numbers")
            distance, duration = float(distance), float(duration)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderResponseError(f"ORS route feature is malformed: {exc}") from exc
        if not (math.isfinite(distance) and math.isfinite(duration)):
            raise ProviderResponseError("ORS route summary contains non-finite numbers")
        return Route(points=points, distance_m=distance, duration_s=duration, strategy="provider")


def _error_details(response: requests.Response) -> tuple[int | None, str]:
    """Extract (code, message) from an ORS error body, tolerating other shapes."""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None, "no error details"
    if isinstance(error, dict):
        code = error.get("code")
        return (code if isinstance(code, int) else None), str(error.get("message", ""))[:300]
    return None, str(error)[:300] if error else "no error details"
