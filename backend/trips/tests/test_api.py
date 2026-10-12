"""POST /api/v1/routes/assess/ contract tests. Providers are faked; no network, no API keys."""

import gzip
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from routing.errors import (
    NoRouteFound,
    NoRoutesFoundError,
    ProviderAuthError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from routing.providers.ors import OpenRouteServiceProvider
from routing.tests.factories import DALLAS, LOS_ANGELES, line_points
from routing.tests.test_ors_provider import FakeResponse, FakeSession
from weather.errors import WeatherRateLimitError, WeatherRequestError, WeatherTimeoutError
from weather.types import HourlyRecord

from .fakes import FakeRoutingProvider
from .test_assessment import CALM, FakeWeatherProvider, wind

URL = "/api/v1/routes/assess/"
UTC = timezone.utc
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
VALID = {
    "origin": {"latitude": 34.0522, "longitude": -118.2437},
    "destination": {"latitude": 32.7767, "longitude": -96.7970},
    "departure_datetime": "2026-10-14T08:00:00-05:00",
    "load_lb": 42000,
    "checkpoint_interval_miles": 25,
}
SECRET = "TOPSECRET-KEY-123"


def payload(**changes):
    body = json.loads(json.dumps(VALID))
    for key, value in changes.items():
        if value is MISSING:
            body.pop(key, None)
        else:
            body[key] = value
    return body


MISSING = object()


def strict_json(response):
    """Parse the body rejecting NaN/Infinity, which are not valid JSON."""

    def refuse(constant):
        raise AssertionError(f"non-JSON constant {constant!r} in response")

    return json.loads(response.content, parse_constant=refuse)


def baseline_of(routes):
    """The straight baseline route (where the test storms are), found by source, not by id or rank."""
    return next(r for r in routes if r["source"] == "baseline")


def straight_line_lat(lon):
    return LOS_ANGELES.lat + (DALLAS.lat - LOS_ANGELES.lat) * (lon - LOS_ANGELES.lon) / (DALLAS.lon - LOS_ANGELES.lon)


def storm_on_baseline(c, h, mph=50.0):
    """Wind only on the straight baseline route's middle band (via-waypoint routes are >0.1 deg away)."""
    on_baseline = abs(c.lat - straight_line_lat(c.lon)) < 0.1 and -110 < c.lon < -100
    return wind(mph) if on_baseline else CALM


class ApiTestCase(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.routing = FakeRoutingProvider()
        self.weather = FakeWeatherProvider()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch("trips.views.get_routing_provider", side_effect=lambda: self.routing))
        self.stack.enter_context(mock.patch("trips.views.get_weather_provider", side_effect=lambda: self.weather))
        self.stack.enter_context(mock.patch("trips.views.utcnow", return_value=NOW))

    def post(self, body=None, **kwargs):
        return self.client.post(URL, VALID if body is None else body, format="json", **kwargs)

    def ok(self, body=None):
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.content[:500])
        return strict_json(response)

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content[:500])
        data = strict_json(response)
        self.assertEqual(data["error"]["code"], code)
        self.assertEqual(set(data), {"error"})
        return data["error"]


class SuccessContractTests(ApiTestCase):
    def test_full_response_structure_units_and_recommendation(self):
        data = self.ok()
        self.assertEqual(data["api_version"], "v1")
        self.assertEqual(data["request"]["departure_datetime"], "2026-10-14T13:00:00Z")
        self.assertEqual(data["request"]["departure_datetime_input"], "2026-10-14T08:00:00-05:00")
        self.assertEqual((data["request"]["load_lb"], data["request"]["checkpoint_interval_miles"]), (42000, 25))
        self.assertEqual(data["request"]["origin"], VALID["origin"])
        self.assertEqual(data["units"]["distance"], "mi")
        self.assertEqual(data["units"]["wind_speed"], "mph")
        self.assertIn("longitude, latitude", data["units"]["geometry_coordinates"])
        self.assertEqual([lv["key"] for lv in data["risk_levels"]], ["low", "moderate", "high", "severe", "no_travel"])

        rec = data["recommendation"]
        self.assertEqual(rec["status"], "recommended")
        self.assertIn("not a guarantee of safety", rec["explanation"])
        self.assertEqual(len(data["routes"]), 3)  # all candidates, not just the winner
        self.assertEqual(rec["recommended_route_id"], data["routes"][0]["id"])

        method = data["method"]
        self.assertEqual(method["wind_metric"], "sustained")
        self.assertEqual(method["min_weather_coverage_percent"], 80)
        self.assertEqual(method["routing"]["profile"], "driving-hgv")
        self.assertEqual(method["routing"]["status"], "complete")
        self.assertTrue(any("Provider alternatives skipped" in n for n in method["routing"]["notes"]))
        self.assertTrue(any("not a guarantee" in a for a in method["assumptions"]))
        self.assertEqual(method["weather"]["attribution"]["license"], "CC BY 4.0")

    def test_route_fields_geojson_geometry_and_timestamps(self):
        data = self.ok()
        for route in data["routes"]:
            self.assertEqual(
                set(route),
                {"id", "source", "rank", "recommended", "eligible", "ineligible_reason", "distance_miles",
                 "duration_seconds", "duration_text", "departure_datetime", "arrival_datetime", "geometry",
                 "risk_summary", "ranking", "checkpoints"},
            )
            geometry = route["geometry"]
            self.assertEqual(geometry["type"], "LineString")
            self.assertEqual(geometry["coordinates"][0], [-118.2437, 34.0522])  # [lon, lat]
            self.assertEqual(geometry["coordinates"][-1], [-96.797, 32.7767])
            self.assertTrue(all(len(c) == 2 and -180 <= c[0] <= 180 and -90 <= c[1] <= 90 for c in geometry["coordinates"]))
            self.assertIsInstance(route["distance_miles"], float)
            self.assertIsInstance(route["duration_seconds"], int)
            self.assertRegex(route["duration_text"], r"^\d+ h \d+ min$")
            self.assertEqual(route["departure_datetime"], "2026-10-14T13:00:00Z")
            arrival = self.parse(route["arrival_datetime"])
            self.assertAlmostEqual((arrival - self.parse(route["departure_datetime"])).total_seconds(), route["duration_seconds"], delta=1)

    @staticmethod
    def parse(text):
        assert text.endswith("Z"), text
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        return parsed

    def test_checkpoints_progress_along_route_with_units_and_weather(self):
        route = self.ok()["routes"][0]
        cps = route["checkpoints"]
        self.assertEqual(cps[0]["distance_miles"], 0)
        self.assertAlmostEqual(cps[-1]["distance_miles"], route["distance_miles"], delta=0.1)
        self.assertTrue(all(b["distance_miles"] > a["distance_miles"] for a, b in zip(cps, cps[1:])))
        etas = [self.parse(c["eta"]) for c in cps]
        self.assertTrue(all(b > a for a, b in zip(etas, etas[1:])))
        self.assertEqual(etas[0], datetime(2026, 10, 14, 13, tzinfo=UTC))
        self.assertAlmostEqual(sum(c["segment_miles"] for c in cps), route["distance_miles"], delta=0.5)

        cp = cps[1]
        self.assertEqual(set(cp["weather"]), {"wind_speed_mph", "wind_gust_mph", "rain_in_per_hr", "snow_in_per_hr", "wind_used_mph"})
        self.assertEqual(cp["weather"]["wind_speed_mph"], 5.0)
        self.assertEqual(cp["weather_status"], "complete")
        self.assertIsNone(cp["weather_missing_reason"])
        self.assertEqual(cp["risk"]["combined"], "low")
        self.assertEqual({"combined", "wind", "rain", "snow", "load_override", "reasons"}, set(cp["risk"]))
        self.assertTrue(-90 <= cp["latitude"] <= 90 and -180 <= cp["longitude"] <= 180)

    def test_risk_summary_miles_cover_the_whole_route(self):
        for route in self.ok()["routes"]:
            s = route["risk_summary"]
            self.assertEqual(set(s["miles"]), {"low", "moderate", "high", "severe", "no_travel", "unknown"})
            self.assertAlmostEqual(sum(s["miles"].values()), route["distance_miles"], delta=0.5)
            self.assertEqual(s["weather_coverage_percent"], 100.0)
            self.assertEqual(s["average_score"], 0.0)

    def test_supported_checkpoint_intervals(self):
        counts = {}
        for interval in (10, 25, 50, 25.0):
            data = self.ok(payload(checkpoint_interval_miles=interval))
            self.assertEqual(data["method"]["checkpoint_interval_miles"], int(interval))
            counts[interval] = len(data["routes"][0]["checkpoints"])
        self.assertGreater(counts[10], counts[25])
        self.assertGreater(counts[25], counts[50])
        self.assertEqual(counts[25], counts[25.0])

    def test_response_is_gzipped_when_requested(self):
        response = self.client.post(URL, VALID, format="json", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(response["Content-Encoding"], "gzip")
        self.assertEqual(json.loads(gzip.decompress(response.content))["api_version"], "v1")

    def test_response_never_contains_the_api_key(self):
        with override_settings(ORS_API_KEY=SECRET):
            self.assertNotIn(SECRET, self.post().content.decode())


class RankingAndSafetyTests(ApiTestCase):
    def test_no_travel_route_is_ineligible_ranked_last_and_not_recommended(self):
        self.weather = FakeWeatherProvider(storm_on_baseline)
        data = self.ok()
        baseline = baseline_of(data["routes"])
        self.assertFalse(baseline["eligible"])
        self.assertGreater(baseline["risk_summary"]["miles"]["no_travel"], 0)
        self.assertGreater(baseline["risk_summary"]["no_travel_checkpoints"], 0)
        self.assertIn("No Travel", baseline["ineligible_reason"])
        self.assertEqual(data["routes"][-1]["id"], baseline["id"])
        self.assertEqual(baseline["ranking"]["explanation"], f"Not eligible for recommendation: {baseline['ineligible_reason']}.")
        self.assertNotEqual(data["recommendation"]["recommended_route_id"], baseline["id"])
        self.assertEqual(data["recommendation"]["status"], "recommended")
        no_travel_cp = next(c for c in baseline["checkpoints"] if c["risk"]["combined"] == "no_travel")
        self.assertEqual(no_travel_cp["risk"]["load_override"], "no_travel")
        self.assertTrue(any("load" in reason for reason in no_travel_cp["risk"]["reasons"]))
        self.assertEqual(no_travel_cp["risk"]["wind"], "severe")

    def test_load_override_boundary_through_the_api(self):
        self.weather = FakeWeatherProvider(storm_on_baseline)
        light = self.ok(payload(load_lb=30000))["routes"]
        heavy = self.ok(payload(load_lb=30001))["routes"]
        self.assertEqual(baseline_of(light)["risk_summary"]["no_travel_checkpoints"], 0)
        self.assertGreater(baseline_of(heavy)["risk_summary"]["no_travel_checkpoints"], 0)

    def test_ranking_order_and_recommendation_are_consistent(self):
        # 40 mph with a 42,000 lb load is Severe on the baseline route's band, Low elsewhere.
        self.weather = FakeWeatherProvider(lambda c, h: storm_on_baseline(c, h, mph=40.0))
        data = self.ok()
        routes = data["routes"]
        self.assertEqual([r["rank"] for r in routes], [1, 2, 3])
        self.assertEqual([r["recommended"] for r in routes], [True, False, False])
        self.assertEqual(data["recommendation"]["recommended_route_id"], routes[0]["id"])
        self.assertTrue(routes[0]["eligible"])
        keys = [
            (
                not r["risk_summary"]["weather_data_complete"],
                r["ranking"]["keys"]["severe_miles"],
                r["ranking"]["keys"]["high_miles"],
                r["ranking"]["keys"]["average_score"],
                r["ranking"]["keys"]["duration_seconds"],
            )
            for r in routes
            if r["eligible"]
        ]
        self.assertEqual(keys, sorted(keys))
        baseline = baseline_of(routes)
        self.assertGreater(baseline["risk_summary"]["miles"]["severe"], 0)
        self.assertEqual(baseline["rank"], 3)
        # Routes 1 and 2 tie on risk, so travel time decides; the Severe-mile route loses on the first criterion.
        self.assertIn("a shorter travel time", routes[0]["ranking"]["explanation"])
        self.assertTrue(routes[1]["ranking"]["explanation"].startswith(f"Ranked below {routes[0]['id']}"))
        self.assertIn("fewer Severe miles (0 vs", routes[2]["ranking"]["explanation"])

    def test_every_route_no_travel_gives_no_safe_route_and_no_recommendation(self):
        self.weather = FakeWeatherProvider(lambda c, h: wind(60.0))
        data = self.ok()
        self.assertEqual(data["recommendation"]["status"], "no_safe_route")
        self.assertIsNone(data["recommendation"]["recommended_route_id"])
        self.assertIn("No route is recommended", data["recommendation"]["explanation"])
        self.assertFalse(any(r["recommended"] or r["eligible"] for r in data["routes"]))
        self.assertEqual(len(data["routes"]), 3)

    def test_insufficient_weather_means_no_recommendation_and_never_zero_weather(self):
        departure = (NOW + timedelta(days=30)).isoformat()  # far beyond the 16-day forecast horizon
        data = self.ok(payload(departure_datetime=departure))
        self.assertEqual(data["recommendation"]["status"], "insufficient_weather_data")
        self.assertIsNone(data["recommendation"]["recommended_route_id"])
        self.assertIn("does not mean conditions are safe", data["recommendation"]["explanation"])
        self.assertEqual(self.weather.calls, [])  # nothing requested outside the available range
        for route in data["routes"]:
            self.assertFalse(route["eligible"])
            self.assertEqual(route["risk_summary"]["weather_coverage_percent"], 0.0)
            self.assertAlmostEqual(route["risk_summary"]["miles"]["unknown"], route["distance_miles"], delta=0.1)
            self.assertIsNone(route["risk_summary"]["average_score"])
            for cp in route["checkpoints"]:
                self.assertEqual(cp["weather_status"], "unavailable")
                self.assertIn("beyond the forecast horizon", cp["weather_missing_reason"])
                self.assertTrue(all(v is None for v in cp["weather"].values()))  # null, never 0
                self.assertIsNone(cp["risk"]["combined"])

    def test_partial_weather_fields_are_preserved_with_reason(self):
        self.weather = FakeWeatherProvider(lambda c, h: HourlyRecord(10.0, 15.0, None, 0.0))  # rain missing
        data = self.ok()
        cp = data["routes"][0]["checkpoints"][1]
        self.assertEqual(cp["weather_status"], "partial")
        self.assertIn("rain", cp["weather_missing_reason"])
        self.assertIsNone(cp["weather"]["rain_in_per_hr"])
        self.assertEqual(cp["weather"]["snow_in_per_hr"], 0.0)
        self.assertEqual(cp["risk"]["combined"], "low")  # known hazards still classified
        self.assertIsNone(cp["risk"]["rain"])
        self.assertEqual(data["recommendation"]["status"], "recommended_incomplete_weather")
        self.assertFalse(data["routes"][0]["risk_summary"]["weather_data_complete"])
        self.assertIn("may be understated", data["recommendation"]["explanation"])

    def test_missing_hours_leave_null_measurements_for_those_checkpoints(self):
        self.weather = FakeWeatherProvider(lambda c, h: None if h.hour == 15 else CALM)
        route = self.ok()["routes"][0]
        missing = [c for c in route["checkpoints"] if c["weather_status"] != "complete"]
        self.assertTrue(missing)
        for cp in missing:
            self.assertIsNotNone(cp["weather_missing_reason"])
            self.assertIsNone(cp["weather"]["wind_speed_mph"])
        self.assertLess(route["risk_summary"]["weather_coverage_percent"], 100)
        self.assertGreater(route["risk_summary"]["miles"]["unknown"], 0)

    def test_wind_metric_setting_is_reported_and_used(self):
        self.weather = FakeWeatherProvider(lambda c, h: HourlyRecord(20.0, 60.0, 0.0, 0.0))
        with override_settings(WEATHER_WIND_METRIC="gust"):
            data = self.ok()
        self.assertEqual(data["method"]["wind_metric"], "gust")
        cp = data["routes"][0]["checkpoints"][1]
        self.assertEqual((cp["weather"]["wind_used_mph"], cp["risk"]["combined"]), (60.0, "no_travel"))
        self.assertTrue(any("gusts" in a for a in data["method"]["assumptions"]))


class ValidationTests(ApiTestCase):
    CASES = [
        ("origin missing", payload(origin=MISSING), "origin"),
        ("origin latitude missing", payload(origin={"longitude": 1.0}), "origin.latitude"),
        ("origin not object", payload(origin="LA"), "origin"),
        ("latitude too high", payload(origin={"latitude": 90.5, "longitude": 0}), "origin.latitude"),
        ("latitude too low", payload(origin={"latitude": -91, "longitude": 0}), "origin.latitude"),
        ("longitude too high", payload(destination={"latitude": 0, "longitude": 180.1}), "destination.longitude"),
        ("latitude string", payload(origin={"latitude": "34.05", "longitude": -118.2}), "origin.latitude"),
        ("latitude bool", payload(origin={"latitude": True, "longitude": -118.2}), "origin.latitude"),
        ("latitude null", payload(origin={"latitude": None, "longitude": -118.2}), "origin.latitude"),
        ("destination missing", payload(destination=MISSING), "destination"),
        ("departure missing", payload(departure_datetime=MISSING), "departure_datetime"),
        ("departure naive", payload(departure_datetime="2026-10-14T08:00:00"), "departure_datetime"),
        ("departure date only", payload(departure_datetime="2026-10-14"), "departure_datetime"),
        ("departure garbage", payload(departure_datetime="tomorrow morning"), "departure_datetime"),
        ("departure number", payload(departure_datetime=1760000000), "departure_datetime"),
        ("load missing", payload(load_lb=MISSING), "load_lb"),
        ("load zero", payload(load_lb=0), "load_lb"),
        ("load negative", payload(load_lb=-5), "load_lb"),
        ("load string", payload(load_lb="42000"), "load_lb"),
        ("load bool", payload(load_lb=True), "load_lb"),
        ("load too large", payload(load_lb=150001), "load_lb"),
        ("load null", payload(load_lb=None), "load_lb"),
        ("interval missing", payload(checkpoint_interval_miles=MISSING), "checkpoint_interval_miles"),
        ("interval unsupported", payload(checkpoint_interval_miles=30), "checkpoint_interval_miles"),
        ("interval zero", payload(checkpoint_interval_miles=0), "checkpoint_interval_miles"),
        ("interval string", payload(checkpoint_interval_miles="25"), "checkpoint_interval_miles"),
        ("interval bool", payload(checkpoint_interval_miles=True), "checkpoint_interval_miles"),
        ("same origin and destination", payload(destination=VALID["origin"]), "destination"),
        ("nearly same point", payload(destination={"latitude": 34.0523, "longitude": -118.2437}), "destination"),
    ]

    def test_invalid_input_gives_400_with_field_level_errors_and_calls_no_provider(self):
        for name, body, field in self.CASES:
            with self.subTest(name):
                error = self.assert_error(self.post(body), 400, "validation_error")
                self.assertTrue(
                    any(key == field or key.startswith(field + ".") for key in error["fields"]),
                    f"{field} not in {list(error['fields'])}",
                )
                self.assertTrue(all(isinstance(v, list) and v for v in error["fields"].values()))
        self.assertEqual((self.routing.calls, self.weather.calls), ([], []))

    def test_all_problems_are_reported_together(self):
        body = payload(load_lb=-1, checkpoint_interval_miles=7, departure_datetime="nope")
        error = self.assert_error(self.post(body), 400, "validation_error")
        self.assertEqual(set(error["fields"]), {"load_lb", "checkpoint_interval_miles", "departure_datetime"})

    def test_empty_body_lists_every_required_field(self):
        response = self.client.post(URL, "", content_type="application/json")
        error = self.assert_error(response, 400, "validation_error")
        self.assertEqual(
            set(error["fields"]),
            {"origin", "destination", "departure_datetime", "load_lb", "checkpoint_interval_miles"},
        )

    def test_json_body_that_is_not_an_object(self):
        error = self.assert_error(self.client.post(URL, [1, 2], format="json"), 400, "validation_error")
        self.assertIn("body", error["fields"])

    def test_malformed_json(self):
        for raw in ("{bad json", '{"load_lb": NaN}'):
            with self.subTest(raw):
                response = self.client.post(URL, raw, content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(strict_json(response)["error"]["code"], "invalid_json")

    def test_wrong_content_type_and_method(self):
        self.assert_error(self.client.post(URL, "x=1", content_type="text/plain"), 415, "unsupported_media_type")
        self.assert_error(self.client.get(URL), 405, "method_not_allowed")


class ProviderFailureTests(ApiTestCase):
    def test_routing_failures_map_to_gateway_statuses(self):
        cases = [
            (ProviderTimeoutError("took 30s"), 504, "routing_timeout"),
            (ProviderConnectionError("dns failure"), 502, "routing_failed"),
            (ProviderResponseError("garbage payload"), 502, "routing_failed"),
            (ProviderRateLimitError("quota"), 503, "routing_rate_limited"),
            (ProviderAuthError("bad key"), 503, "routing_unavailable"),
            (ProviderConfigurationError("ORS_API_KEY is not set"), 503, "routing_unavailable"),
            (NoRouteFound("no route", status_code=404, code=2010), 422, "no_route_found"),
            (NoRoutesFoundError("nothing valid | notes"), 422, "no_route_found"),
        ]
        for exc, status, code in cases:
            with self.subTest(code=code, exc=type(exc).__name__):
                self.routing = FakeRoutingProvider(error=exc)
                with self.assertLogs("trips.views", level="WARNING"):
                    response = self.post()
                error = self.assert_error(response, status, code)
                for internal in ("ORS_API_KEY", "dns failure", "garbage payload", "took 30s", "Traceback", "bad key"):
                    self.assertNotIn(internal, response.content.decode())
                self.assertEqual(set(error), {"code", "message"})

    def test_routing_failure_is_never_a_successful_empty_response(self):
        self.routing = FakeRoutingProvider(error=ProviderTimeoutError("slow"))
        with self.assertLogs("trips.views", level="WARNING"):
            response = self.post()
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("routes", strict_json(response))

    def test_weather_failures_map_to_gateway_statuses(self):
        cases = [
            (WeatherTimeoutError("took 20s"), 504, "weather_timeout"),
            (WeatherRateLimitError("429"), 503, "weather_rate_limited"),
            (WeatherRequestError("Open-Meteo HTTP 400: secret reason", status_code=400), 502, "weather_failed"),
        ]
        for exc, status, code in cases:
            with self.subTest(code=code):
                self.weather = FakeWeatherProvider(error=exc)
                with self.assertLogs("trips.views", level="WARNING"):
                    response = self.post()
                self.assert_error(response, status, code)
                self.assertNotIn("secret reason", response.content.decode())

    def test_unexpected_error_gives_generic_500_without_internals(self):
        with mock.patch("trips.views.assess_trip", side_effect=RuntimeError("SECRET-INTERNAL-DETAIL")):
            with self.assertLogs("trips.views", level="ERROR"):
                response = self.post()
        error = self.assert_error(response, 500, "internal_error")
        self.assertEqual(error["message"], "An unexpected error occurred.")
        body = response.content.decode()
        self.assertNotIn("SECRET-INTERNAL-DETAIL", body)
        self.assertNotIn("Traceback", body)

    def test_real_ors_adapter_errors_do_not_leak_the_api_key(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status):
                session = FakeSession(FakeResponse(status, {"error": {"code": 1000, "message": "provider text"}}))
                self.routing = OpenRouteServiceProvider(SECRET, session=session)
                with self.assertLogs("trips.views", level="WARNING") as logs:
                    response = self.post()
                self.assertGreaterEqual(response.status_code, 502)
                self.assertNotIn(SECRET, response.content.decode())
                self.assertNotIn(SECRET, "\n".join(logs.output))  # not in server logs either
                self.assertNotIn("provider text", response.content.decode())

    def test_missing_ors_key_is_reported_as_unavailable_without_naming_settings(self):
        self.routing = OpenRouteServiceProvider("", session=FakeSession(FakeResponse(200, {})))
        with self.assertLogs("trips.views", level="WARNING"):
            response = self.post()
        self.assert_error(response, 503, "routing_unavailable")
        self.assertNotIn("ORS_API_KEY", response.content.decode())
