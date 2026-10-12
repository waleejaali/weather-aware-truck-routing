"""ORS adapter tests with mocked HTTP. No network and no API key needed."""

from unittest import TestCase

import requests

from routing.errors import (
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
from routing.providers.ors import OpenRouteServiceProvider
from routing.types import Coordinate

from .factories import LOS_ANGELES, NEAR_LOS_ANGELES

SECRET = "test-secret-key"
ORIGIN, DESTINATION = LOS_ANGELES, NEAR_LOS_ANGELES


class FakeResponse:
    def __init__(self, status_code=200, payload=None, *, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.response


def feature(coords=((-118.2437, 34.0522), (-118.1, 34.1), (-118.0, 34.2)), distance=25_000.0, duration=1_800.0):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [list(c) for c in coords]},
        "properties": {"summary": {"distance": distance, "duration": duration}},
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def provider(session, key=SECRET, **kwargs):
    return OpenRouteServiceProvider(key, session=session, **kwargs)


class OrsSuccessTests(TestCase):
    def test_directions_parses_route_and_swaps_to_lat_lon(self):
        session = FakeSession(FakeResponse(200, collection(feature())))
        route = provider(session).directions([ORIGIN, DESTINATION])
        self.assertEqual(route.points[0], Coordinate(34.0522, -118.2437))  # (lat, lon)
        self.assertEqual((route.distance_m, route.duration_s), (25_000.0, 1_800.0))

    def test_request_shape_profile_and_key_placement(self):
        session = FakeSession(FakeResponse(200, collection(feature())))
        provider(session, base_url="https://ors.example/").directions(
            [ORIGIN, Coordinate(34.1, -118.1), DESTINATION], preference="shortest"
        )
        call = session.calls[0]
        self.assertEqual(call["url"], "https://ors.example/v2/directions/driving-hgv/geojson")
        self.assertEqual(call["headers"]["Authorization"], SECRET)
        self.assertNotIn(SECRET, call["url"])
        self.assertEqual(call["json"]["coordinates"][0], [-118.2437, 34.0522])  # [lon, lat]
        self.assertEqual(call["json"]["preference"], "shortest")
        self.assertEqual(len(call["json"]["radiuses"]), 3)
        self.assertNotIn("alternative_routes", call["json"])

    def test_alternative_routes_request_and_multiple_features(self):
        session = FakeSession(FakeResponse(200, collection(feature(), feature(distance=26_000.0))))
        routes = provider(session).alternative_routes(ORIGIN, DESTINATION, 3)
        self.assertEqual(len(routes), 2)
        self.assertEqual(session.calls[0]["json"]["alternative_routes"]["target_count"], 3)

    def test_profile_is_explicit_and_configurable(self):
        session = FakeSession(FakeResponse(200, collection(feature())))
        provider(session, profile="driving-car").directions([ORIGIN, DESTINATION])
        self.assertIn("/driving-car/", session.calls[0]["url"])


class OrsErrorTests(TestCase):
    def call(self, session, alternatives=False):
        p = provider(session)
        if alternatives:
            return p.alternative_routes(ORIGIN, DESTINATION, 3)
        return p.directions([ORIGIN, DESTINATION])

    def error(self, status, code=None, message="boom"):
        payload = {"error": {"code": code, "message": message}} if code else {"error": message}
        return FakeSession(FakeResponse(status, payload))

    def test_long_distance_alternatives_rejected(self):
        session = self.error(400, 2004, "approximated route distance must not be greater than 100000.0 meters")
        with self.assertRaises(AlternativeRoutesUnavailable):
            self.call(session, alternatives=True)

    def test_code_2004_on_plain_directions_is_a_generic_request_error(self):
        with self.assertRaises(ProviderRequestError) as ctx:
            self.call(self.error(400, 2004))
        self.assertNotIsInstance(ctx.exception, AlternativeRoutesUnavailable)

    def test_no_route_found(self):
        with self.assertRaises(NoRouteFound):
            self.call(self.error(404, 2010, "Could not find routable point"))

    def test_auth_and_rate_limit(self):
        with self.assertRaises(ProviderAuthError):
            self.call(self.error(403))
        with self.assertRaises(ProviderRateLimitError):
            self.call(self.error(429))

    def test_server_error(self):
        with self.assertRaises(ProviderRequestError) as ctx:
            self.call(self.error(500))
        self.assertEqual(ctx.exception.status_code, 500)

    def test_timeout_and_connection_errors(self):
        with self.assertRaises(ProviderTimeoutError):
            self.call(FakeSession(exc=requests.Timeout()))
        with self.assertRaises(ProviderConnectionError):
            self.call(FakeSession(exc=requests.ConnectionError()))

    def test_invalid_responses(self):
        bad_payloads = [
            FakeResponse(200, bad_json=True),
            FakeResponse(200, ["not", "a", "dict"]),
            FakeResponse(200, {"features": "nope"}),
            FakeResponse(200, collection({"geometry": {"type": "LineString", "coordinates": []}})),
            FakeResponse(200, collection(feature(distance="far"))),
            FakeResponse(200, collection(feature(distance=float("inf")))),
            FakeResponse(200, collection(feature(coords=[[1.0]]))),
        ]
        for response in bad_payloads:
            with self.subTest(response=response._payload):
                with self.assertRaises(ProviderResponseError):
                    self.call(FakeSession(response))

    def test_directions_with_no_features_is_an_error(self):
        with self.assertRaises(ProviderResponseError):
            self.call(FakeSession(FakeResponse(200, collection())))

    def test_missing_api_key_fails_before_any_request(self):
        session = FakeSession(FakeResponse(200, collection(feature())))
        with self.assertRaisesRegex(ProviderConfigurationError, "ORS_API_KEY"):
            provider(session, key="").directions([ORIGIN, DESTINATION])
        self.assertEqual(session.calls, [])

    def test_error_messages_never_contain_the_key(self):
        try:
            self.call(self.error(403, message="Access to this API has been disallowed"))
        except ProviderAuthError as exc:
            self.assertNotIn(SECRET, str(exc))
