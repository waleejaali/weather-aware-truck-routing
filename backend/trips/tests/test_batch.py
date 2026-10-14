from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from routing.errors import ProviderTimeoutError
from routing.providers.ors import OpenRouteServiceProvider
from routing.tests.factories import DALLAS, LOS_ANGELES, NEAR_LOS_ANGELES
from routing.tests.test_ors_provider import FakeResponse, FakeSession
from routing.types import Coordinate
from trips.batch import PrimedWeatherProvider, plan_routes_cached, route_cache_key
from trips.serializers import MAX_BATCH_DEPARTURES
from weather.errors import WeatherTimeoutError
from weather.types import HourlySeries

from .fakes import FakeRoutingProvider
from .test_api import MISSING, NOW, VALID, ApiTestCase, straight_line_lat, strict_json, wind
from .test_assessment import CALM, FakeWeatherProvider

BATCH_URL = "/api/v1/routes/assess-batch/"
SINGLE_URL = "/api/v1/routes/assess/"
D0 = "2026-10-14T08:00:00-05:00"  # 13:00Z
D1 = "2026-10-14T14:00:00-05:00"
D2 = "2026-10-14T20:00:00-05:00"


def batch_payload(departures=(D0, D1, D2), **changes):
    body = {k: v for k, v in VALID.items() if k != "departure_datetime"}
    body["departure_datetimes"] = list(departures)
    for key, value in changes.items():
        if value is MISSING:
            body.pop(key, None)
        else:
            body[key] = value
    return body


def storm_only_for_first_departure(c, h):
    on_baseline = abs(c.lat - straight_line_lat(c.lon)) < 0.1 and -110 < c.lon < -100
    in_storm_window = datetime(2026, 10, 14, 20, tzinfo=timezone.utc) <= h <= datetime(2026, 10, 15, 2, tzinfo=timezone.utc)
    return wind(50.0) if on_baseline and in_storm_window else CALM


def without_geometry(route):
    return {k: v for k, v in route.items() if k != "geometry"}


class BatchTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        caches["routes"].clear()
        self.addCleanup(caches["routes"].clear)

    def post_batch(self, body=None, **kwargs):
        return self.client.post(BATCH_URL, batch_payload() if body is None else body, format="json", **kwargs)

    def ok_batch(self, body=None):
        response = self.post_batch(body)
        self.assertEqual(response.status_code, 200, response.content[:600])
        return strict_json(response)

    def single(self, departure):
        body = {k: v for k, v in VALID.items()}
        body["departure_datetime"] = departure
        response = self.client.post(SINGLE_URL, body, format="json")
        self.assertEqual(response.status_code, 200, response.content[:600])
        return strict_json(response)


class BatchContractTests(BatchTestCase):
    def test_one_result_per_departure_in_request_order_with_shared_geometry(self):
        data = self.ok_batch()
        self.assertEqual(data["api_version"], "v1")
        self.assertEqual(data["request"]["departure_datetimes"], ["2026-10-14T13:00:00Z", "2026-10-14T19:00:00Z", "2026-10-15T01:00:00Z"])
        self.assertEqual([r["index"] for r in data["results"]], [0, 1, 2])
        self.assertEqual([r["departure_datetime_input"] for r in data["results"]], [D0, D1, D2])
        self.assertEqual([r["departure_datetime"] for r in data["results"]], data["request"]["departure_datetimes"])
        self.assertTrue(all(r["ok"] for r in data["results"]))
        self.assertTrue(data["generated_at"].endswith("Z"))
        self.assertEqual(data["units"]["wind_speed"], "mph")
        self.assertEqual(data["method"]["wind_metric"], "sustained")
        self.assertEqual(data["method"]["weather"]["attribution"]["license"], "CC BY 4.0")

        self.assertEqual(len(data["routes"]), 3)
        for shared in data["routes"]:
            self.assertEqual(shared["geometry"]["type"], "LineString")
            self.assertEqual(shared["geometry"]["coordinates"][0], [-118.2437, 34.0522])
        for result in data["results"]:
            self.assertEqual({r["id"] for r in result["routes"]}, {s["id"] for s in data["routes"]})
            self.assertTrue(all("geometry" not in r for r in result["routes"]))

    def test_each_departure_has_its_own_etas_and_weather(self):
        self.weather = FakeWeatherProvider(storm_only_for_first_departure)
        data = self.ok_batch()
        first_etas = []
        for i, result in enumerate(data["results"]):
            route = result["routes"][0]
            etas = [c["eta"] for c in route["checkpoints"]]
            self.assertEqual(etas[0], data["request"]["departure_datetimes"][i])
            self.assertEqual(route["departure_datetime"], data["request"]["departure_datetimes"][i])
            first_etas.append(etas[0])
        self.assertEqual(len(set(first_etas)), 3)

        baselines = {}
        for result in data["results"]:
            shared_id = next(s["id"] for s in data["routes"] if s["source"] == "baseline")
            baselines[result["index"]] = next(r for r in result["routes"] if r["id"] == shared_id)
        self.assertFalse(baselines[0]["eligible"])
        self.assertGreater(baselines[0]["risk_summary"]["no_travel_checkpoints"], 0)
        self.assertTrue(baselines[1]["eligible"])
        self.assertTrue(baselines[2]["eligible"])
        self.assertNotEqual(data["results"][0]["recommendation"]["recommended_route_id"], baselines[0]["id"])

    def test_every_result_matches_the_single_departure_endpoint(self):
        self.weather = FakeWeatherProvider(storm_only_for_first_departure)
        batch = self.ok_batch()
        shared = {s["id"]: s for s in batch["routes"]}
        for result, departure in zip(batch["results"], (D0, D1, D2)):
            single = self.single(departure)
            self.assertEqual(result["recommendation"], single["recommendation"])
            self.assertEqual(result["notes"], single["method"]["notes"])
            self.assertEqual([without_geometry(r) for r in single["routes"]], result["routes"])
            for route in single["routes"]:
                self.assertEqual(shared[route["id"]]["geometry"], route["geometry"])
        self.assertEqual(batch["method"]["assumptions"], single["method"]["assumptions"])
        self.assertEqual(batch["method"]["routing"], single["method"]["routing"])

    def test_ranking_and_recommendation_are_consistent_within_each_result(self):
        self.weather = FakeWeatherProvider(storm_only_for_first_departure)
        for result in self.ok_batch()["results"]:
            ranks = [r["rank"] for r in result["routes"]]
            self.assertEqual(ranks, list(range(1, len(ranks) + 1)))
            rec = result["recommendation"]["recommended_route_id"]
            first = result["routes"][0]
            self.assertEqual(rec, first["id"] if first["eligible"] else None)
            self.assertEqual([r["recommended"] for r in result["routes"]], [r["id"] == rec for r in result["routes"]])

    def test_missing_weather_is_reported_per_departure_and_never_as_safe(self):
        far = (NOW + timedelta(days=30)).isoformat()
        data = self.ok_batch(batch_payload(departures=(D0, far)))
        good, bad = data["results"]
        self.assertEqual(good["recommendation"]["status"], "recommended")
        self.assertEqual(bad["recommendation"]["status"], "insufficient_weather_data")
        self.assertIsNone(bad["recommendation"]["recommended_route_id"])
        for route in bad["routes"]:
            self.assertFalse(route["eligible"])
            self.assertEqual(route["risk_summary"]["weather_coverage_percent"], 0.0)
            for cp in route["checkpoints"]:
                self.assertEqual(cp["weather_status"], "unavailable")
                self.assertTrue(all(v is None for v in cp["weather"].values()))
        self.assertEqual(len(self.weather.calls), 1)

    def test_batch_of_the_maximum_size_works(self):
        departures = [(NOW + timedelta(days=1, hours=i)).isoformat() for i in range(MAX_BATCH_DEPARTURES)]
        data = self.ok_batch(batch_payload(departures=departures))
        self.assertEqual(len(data["results"]), MAX_BATCH_DEPARTURES)


class ReuseTests(BatchTestCase):
    def test_routes_are_planned_once_where_separate_requests_plan_every_time(self):
        probe = FakeRoutingProvider()
        self.routing = probe
        self.single(D0)
        calls_per_plan = len(probe.calls)
        self.assertGreater(calls_per_plan, 1)

        self.routing = FakeRoutingProvider()
        data = self.ok_batch()
        self.assertEqual(len(self.routing.calls), calls_per_plan)
        self.assertEqual(data["diagnostics"]["route_cache"], "miss")
        self.assertEqual(data["diagnostics"]["routing_provider_requests"], calls_per_plan)

    def test_weather_is_fetched_once_for_all_departures(self):
        data = self.ok_batch()
        self.assertEqual(len(self.weather.calls), 1)
        self.assertEqual(data["diagnostics"]["weather_provider_requests"], 1)
        locations, start, end = self.weather.calls[0]
        self.assertEqual(len(locations), len(set(locations)))
        longest = max(r["duration_seconds"] for r in data["routes"])
        self.assertLessEqual(start, datetime(2026, 10, 14, 13, tzinfo=timezone.utc))
        self.assertGreaterEqual(end, datetime(2026, 10, 15, 1, tzinfo=timezone.utc) + timedelta(seconds=longest))

    def test_second_identical_request_reuses_the_cached_plan(self):
        self.ok_batch()
        planned = len(self.routing.calls)
        data = self.ok_batch()
        self.assertEqual(len(self.routing.calls), planned)
        self.assertEqual(data["diagnostics"], {"route_cache": "hit", "routing_provider_requests": 0, "weather_provider_requests": 1})

    def test_load_interval_and_departures_do_not_affect_the_route_cache_key(self):
        self.ok_batch()
        planned = len(self.routing.calls)
        for changes in (dict(load_lb=12000), dict(checkpoint_interval_miles=50), dict(departures=(D2,))):
            body = batch_payload(**{k: v for k, v in changes.items() if k != "departures"}) if "departures" not in changes else batch_payload(departures=changes["departures"])
            data = self.ok_batch(body)
            self.assertEqual(data["diagnostics"]["route_cache"], "hit", changes)
        self.assertEqual(len(self.routing.calls), planned)

    def test_routing_relevant_inputs_do_change_the_key(self):
        provider = FakeRoutingProvider()
        keys = {
            route_cache_key(LOS_ANGELES, DALLAS, provider, _config()),
            route_cache_key(LOS_ANGELES, NEAR_LOS_ANGELES, provider, _config()),
            route_cache_key(NEAR_LOS_ANGELES, DALLAS, provider, _config()),
            route_cache_key(Coordinate(34.0523, -118.2437), DALLAS, provider, _config()),
        }
        self.assertEqual(len(keys), 4)
        other_profile = FakeRoutingProvider()
        other_profile.profile = "driving-car"
        self.assertNotEqual(route_cache_key(LOS_ANGELES, DALLAS, provider, _config()), route_cache_key(LOS_ANGELES, DALLAS, other_profile, _config()))
        self.assertNotEqual(route_cache_key(LOS_ANGELES, DALLAS, provider, _config()), route_cache_key(LOS_ANGELES, DALLAS, provider, _config(max_provider_requests=3)))

    def test_a_different_destination_plans_again(self):
        self.ok_batch()
        planned = len(self.routing.calls)
        other = batch_payload(destination={"latitude": 35.4676, "longitude": -97.5164})
        self.assertEqual(self.ok_batch(other)["diagnostics"]["route_cache"], "miss")
        self.assertGreater(len(self.routing.calls), planned)

    def test_cache_can_be_disabled(self):
        with override_settings(ROUTE_CACHE_TTL_SECONDS=0):
            self.ok_batch()
            planned = len(self.routing.calls)
            self.assertEqual(self.ok_batch()["diagnostics"]["route_cache"], "miss")
        self.assertEqual(len(self.routing.calls), planned * 2)

    def test_cached_plans_expire(self):
        cache = caches["routes"]
        provider = FakeRoutingProvider()
        # Django sets expiry in backends.base but checks it in backends.locmem, so both need the fake clock
        fake_time = mock.Mock()
        with mock.patch("django.core.cache.backends.locmem.time", fake_time), mock.patch("django.core.cache.backends.base.time", fake_time):
            fake_time.time.return_value = 1_000.0
            _, hit, _ = plan_routes_cached(LOS_ANGELES, DALLAS, provider, cache=cache, ttl=60)
            self.assertFalse(hit)
            fake_time.time.return_value = 1_030.0
            self.assertTrue(plan_routes_cached(LOS_ANGELES, DALLAS, provider, cache=cache, ttl=60)[1])
            fake_time.time.return_value = 1_061.0
            self.assertFalse(plan_routes_cached(LOS_ANGELES, DALLAS, provider, cache=cache, ttl=60)[1])

    def test_failures_are_never_cached(self):
        self.routing = FakeRoutingProvider(error=ProviderTimeoutError("slow"))
        with self.assertLogs("trips.views", level="WARNING"):
            self.assertEqual(self.post_batch().status_code, 504)
        self.routing = FakeRoutingProvider()
        data = self.ok_batch()
        self.assertEqual(data["diagnostics"]["route_cache"], "miss")

    def test_a_broken_cache_degrades_to_planning_every_time(self):
        class BrokenCache:
            def get(self, *a, **k):
                raise RuntimeError("cache down")

            set = get

        with mock.patch("trips.batch.caches", {"routes": BrokenCache()}):
            with self.assertLogs("trips.batch", level="WARNING"):
                data = self.ok_batch()
        self.assertEqual(data["diagnostics"]["route_cache"], "miss")
        self.assertEqual(len(data["results"]), 3)


def _config(**kw):
    from routing.services.route_planner import PlannerConfig

    return PlannerConfig(**kw)


class BatchValidationTests(BatchTestCase):
    CASES = [
        ("departures missing", batch_payload(departure_datetimes=MISSING), "departure_datetimes"),
        ("departures empty", batch_payload(departures=()), "departure_datetimes"),
        ("departures not a list", batch_payload(departure_datetimes=D0), "departure_datetimes"),
        ("too many departures", batch_payload(departures=[f"2026-10-{14 + i // 24:02d}T{i % 24:02d}:00:00Z" for i in range(MAX_BATCH_DEPARTURES + 1)]), "departure_datetimes"),
        ("duplicate departures", batch_payload(departures=(D0, D0)), "departure_datetimes"),
        ("same instant, different offsets", batch_payload(departures=("2026-10-14T13:00:00Z", D0)), "departure_datetimes"),
        ("naive departure", batch_payload(departures=(D0, "2026-10-14T14:00:00")), "departure_datetimes.1"),
        ("garbage departure", batch_payload(departures=("soon",)), "departure_datetimes.0"),
        ("numeric departure", batch_payload(departures=(D0, 12345)), "departure_datetimes.1"),
        ("load zero", batch_payload(load_lb=0), "load_lb"),
        ("load too large", batch_payload(load_lb=150001), "load_lb"),
        ("interval unsupported", batch_payload(checkpoint_interval_miles=30), "checkpoint_interval_miles"),
        ("latitude out of range", batch_payload(origin={"latitude": 91, "longitude": 0}), "origin.latitude"),
        ("same origin and destination", batch_payload(destination=VALID["origin"]), "destination"),
        ("origin missing", batch_payload(origin=MISSING), "origin"),
    ]

    def test_invalid_batches_return_400_with_field_errors_and_call_no_provider(self):
        for name, body, field in self.CASES:
            with self.subTest(name):
                response = self.post_batch(body)
                self.assertEqual(response.status_code, 400, response.content[:300])
                error = strict_json(response)["error"]
                self.assertEqual(error["code"], "validation_error")
                self.assertTrue(any(k == field or k.startswith(field + ".") for k in error["fields"]), f"{field} not in {list(error['fields'])}")
        self.assertEqual((self.routing.calls, self.weather.calls), ([], []))

    def test_malformed_json_and_wrong_method(self):
        response = self.client.post(BATCH_URL, "{bad", content_type="application/json")
        self.assertEqual((response.status_code, strict_json(response)["error"]["code"]), (400, "invalid_json"))
        self.assertEqual(self.client.get(BATCH_URL).status_code, 405)


class BatchFailureTests(BatchTestCase):
    def test_routing_failure_fails_the_whole_batch_like_the_single_endpoint(self):
        self.routing = FakeRoutingProvider(error=ProviderTimeoutError("slow"))
        with self.assertLogs("trips.views", level="WARNING"):
            response = self.post_batch()
        self.assertEqual(response.status_code, 504)
        body = strict_json(response)
        self.assertEqual(body["error"]["code"], "routing_timeout")
        self.assertNotIn("results", body)

    def test_shared_weather_failure_fails_the_batch_without_internals(self):
        self.weather = FakeWeatherProvider(error=WeatherTimeoutError("took 20s secret"))
        with self.assertLogs("trips.views", level="WARNING"):
            response = self.post_batch()
        self.assertEqual(response.status_code, 504)
        self.assertEqual(strict_json(response)["error"]["code"], "weather_timeout")
        self.assertNotIn("secret", response.content.decode())

    def test_one_failing_departure_does_not_discard_the_others(self):
        real = __import__("trips.batch", fromlist=["assess_routes"]).assess_routes
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("SECRET-INTERNAL-DETAIL")
            return real(*args, **kwargs)

        with mock.patch("trips.batch.assess_routes", side_effect=flaky), self.assertLogs("trips.batch", level="ERROR"):
            response = self.post_batch()
        self.assertEqual(response.status_code, 200)
        results = strict_json(response)["results"]
        self.assertEqual([r["ok"] for r in results], [True, False, True])
        self.assertEqual(results[1]["error"], {"code": "assessment_failed", "message": "This departure could not be assessed."})
        self.assertEqual(results[1]["departure_datetime_input"], D1)
        self.assertNotIn("routes", results[1])
        self.assertNotIn("SECRET-INTERNAL-DETAIL", response.content.decode())

    def test_every_departure_failing_is_an_error_not_an_empty_success(self):
        with mock.patch("trips.batch.assess_routes", side_effect=RuntimeError("boom")), self.assertLogs("trips.batch", level="ERROR"):
            response = self.post_batch()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(strict_json(response)["error"]["code"], "assessment_failed")

    def test_unexpected_error_gives_a_generic_500(self):
        with mock.patch("trips.views.assess_trip_batch", side_effect=RuntimeError("SECRET-INTERNAL-DETAIL")), self.assertLogs("trips.views", level="ERROR"):
            response = self.post_batch()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("SECRET-INTERNAL-DETAIL", response.content.decode())

    def test_api_key_never_appears_in_batch_errors(self):
        secret = "TOPSECRET-KEY-123"
        self.routing = OpenRouteServiceProvider(secret, session=FakeSession(FakeResponse(403, {"error": {"code": 1000, "message": "nope"}})))
        with self.assertLogs("trips.views", level="WARNING") as logs:
            response = self.post_batch()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(secret, response.content.decode())
        self.assertNotIn(secret, "\n".join(logs.output))


class BackwardCompatibilityTests(BatchTestCase):
    def test_single_endpoint_is_unchanged_and_does_not_use_the_route_cache(self):
        first = self.single(D0)
        planned = len(self.routing.calls)
        self.single(D0)
        self.assertEqual(len(self.routing.calls), planned * 2)
        self.assertIn("departure_datetime", first["request"])
        self.assertNotIn("results", first)
        self.assertTrue(all("geometry" in r for r in first["routes"]))
        self.assertNotIn("diagnostics", first)


class PrimedWeatherProviderTests(SimpleTestCase):
    START = datetime(2026, 10, 14, 0, tzinfo=timezone.utc)

    def inner(self):
        return FakeWeatherProvider()

    def test_serves_primed_locations_without_touching_the_inner_provider_again(self):
        inner = self.inner()
        primed = PrimedWeatherProvider(inner)
        a, b = Coordinate(34.0, -118.0), Coordinate(33.0, -100.0)
        primed.prime([a, b], self.START, self.START + timedelta(hours=48))
        series = primed.fetch_hourly([b, a], self.START + timedelta(hours=5), self.START + timedelta(hours=30))
        self.assertEqual([s.requested for s in series], [b, a])
        self.assertEqual(len(inner.calls), 1)
        self.assertEqual(primed.fallback_fetches, 0)

    def test_falls_back_for_unprimed_locations_and_uncovered_windows(self):
        inner = self.inner()
        primed = PrimedWeatherProvider(inner)
        a = Coordinate(34.0, -118.0)
        primed.prime([a], self.START, self.START + timedelta(hours=10))
        primed.fetch_hourly([Coordinate(1.0, 1.0)], self.START, self.START + timedelta(hours=5))
        primed.fetch_hourly([a], self.START, self.START + timedelta(hours=40))
        self.assertEqual(len(inner.calls), 3)
        self.assertEqual(primed.fallback_fetches, 2)

    def test_does_nothing_up_front_and_never_invents_data_before_priming(self):
        inner = self.inner()
        primed = PrimedWeatherProvider(inner)
        series = primed.fetch_hourly([Coordinate(1.0, 1.0)], self.START, self.START + timedelta(hours=2))
        self.assertIsInstance(series[0], HourlySeries)
        self.assertEqual(len(inner.calls), 1)

    def test_delegates_name_attribution_and_window(self):
        inner = self.inner()
        primed = PrimedWeatherProvider(inner)
        self.assertEqual((primed.name, primed.attribution), (inner.name, inner.attribution))
        self.assertEqual(primed.available_window(NOW), inner.available_window(NOW))

