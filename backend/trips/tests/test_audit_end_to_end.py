"""Audit tests that exercise assessment + API behaviour end to end with fake providers only (no network)."""

import json
from datetime import datetime, timedelta, timezone

from django.core.cache import caches
from unittest import TestCase

from risk.levels import RiskLevel as L
from routing.checkpoints import METERS_PER_MILE, estimate_arrival, sample_checkpoints
from routing.tests.factories import DALLAS, LOS_ANGELES, line_points
from routing.types import Route
from trips.assessment import (
    STATUS_INSUFFICIENT_WEATHER,
    STATUS_NO_SAFE_ROUTE,
    STATUS_RECOMMENDED,
    STATUS_RECOMMENDED_INCOMPLETE,
    assess_routes,
)
from weather.sampling import ceil_hour, floor_hour
from weather.types import HourlyRecord

from .test_api import MISSING, NOW, VALID, ApiTestCase, straight_line_lat, strict_json, wind
from .test_assessment import CALM, DEPARTURE, FakeWeatherProvider, assess
from .test_batch import BATCH_URL, SINGLE_URL, BatchTestCase, batch_payload, without_geometry

UTC = timezone.utc
MI = METERS_PER_MILE


def long_route():
    # 200 mi in 10 h => 50-mile checkpoints are 2.5 h apart
    return Route(tuple(line_points(LOS_ANGELES, DALLAS)), 200 * MI, 10 * 3600.0)


class WeatherSamplerCallContractTests(ApiTestCase):
    """The weather layer must be asked about the right places and the right hours."""

    def test_provider_receives_every_checkpoint_coordinate_and_a_window_covering_every_eta(self):
        route = long_route()
        provider = FakeWeatherProvider()
        assess([route], provider, interval_miles=50)
        [(locations, start, end)] = provider.calls
        checkpoints = sample_checkpoints(route, 50)
        self.assertEqual(locations, [c.coordinate for c in checkpoints])
        etas = [estimate_arrival(DEPARTURE, route, c) for c in checkpoints]
        self.assertEqual(start, floor_hour(min(etas)))
        self.assertEqual(end, ceil_hour(max(etas)))
        self.assertEqual(len(provider.calls), 1)  # one batched request, not one per checkpoint

    def test_checkpoint_etas_in_the_response_match_departure_plus_fraction_of_duration(self):
        data = self.ok()
        departure = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
        for route in data["routes"]:
            for cp in route["checkpoints"]:
                eta = datetime.fromisoformat(cp["eta"].replace("Z", "+00:00"))
                fraction = cp["distance_miles"] / route["distance_miles"]
                expected = departure + timedelta(seconds=route["duration_seconds"] * fraction)
                self.assertAlmostEqual((eta - expected).total_seconds(), 0, delta=120, msg=cp)
            self.assertEqual(route["checkpoints"][0]["eta"], route["departure_datetime"])
            self.assertEqual(route["checkpoints"][-1]["eta"], route["arrival_datetime"])

    def test_weather_comes_from_the_hour_of_arrival_at_each_checkpoint(self):
        route = long_route()
        storm_from = DEPARTURE + timedelta(hours=5, minutes=1)  # the 7.5 h checkpoint (15:30) is first in the storm
        provider = FakeWeatherProvider(lambda c, h: wind(60.0) if h >= storm_from.replace(minute=0) + timedelta(hours=1) else CALM)
        trip = assess([route], provider, interval_miles=50)
        levels = [cp.level for cp in trip.routes[0].checkpoints]
        etas = [cp.eta for cp in trip.routes[0].checkpoints]
        self.assertEqual(levels[0], L.LOW)
        self.assertEqual(levels[-1], L.NO_TRAVEL)
        # strictly monotone: once the storm hour is reached it stays reached
        flipped = [lv == L.NO_TRAVEL for lv in levels]
        self.assertEqual(flipped, sorted(flipped))
        self.assertEqual(etas, sorted(etas))

    def test_gust_metric_changes_the_outcome_only_when_selected(self):
        route = long_route()
        provider = FakeWeatherProvider(lambda c, h: HourlyRecord(10.0, 60.0, 0.0, 0.0))
        sustained = assess([route], provider, wind_metric="sustained")
        gust = assess([route], provider, wind_metric="gust")
        self.assertEqual(sustained.status, STATUS_RECOMMENDED)
        self.assertEqual(gust.status, STATUS_NO_SAFE_ROUTE)
        self.assertEqual(sustained.routes[0].checkpoints[1].wind_mph_used, 10.0)
        self.assertEqual(gust.routes[0].checkpoints[1].wind_mph_used, 60.0)

    def test_a_missing_gust_does_not_degrade_a_sustained_wind_assessment(self):
        provider = FakeWeatherProvider(lambda c, h: HourlyRecord(10.0, None, 0.0, 0.0))
        trip = assess([long_route()], provider, wind_metric="sustained")
        self.assertEqual(trip.status, STATUS_RECOMMENDED)
        self.assertTrue(trip.routes[0].summary.data_complete)

    def test_load_reaches_the_risk_rules(self):
        provider = FakeWeatherProvider(lambda c, h: wind(40.0))
        self.assertEqual(assess([long_route()], provider, load_lb=40_000).routes[0].summary.max_level, L.HIGH)
        self.assertEqual(assess([long_route()], provider, load_lb=40_001).routes[0].summary.max_level, L.SEVERE)


class TruthfulStatusTests(ApiTestCase):
    def test_unavailable_weather_is_null_in_the_payload_never_zero(self):
        self.weather.weather_fn = lambda c, h: None
        data = self.ok()
        self.assertEqual(data["recommendation"]["status"], STATUS_INSUFFICIENT_WEATHER)
        self.assertIsNone(data["recommendation"]["recommended_route_id"])
        for route in data["routes"]:
            self.assertFalse(route["eligible"])
            self.assertEqual(route["risk_summary"]["weather_coverage_percent"], 0.0)
            self.assertIsNone(route["risk_summary"]["average_score"])
            self.assertEqual(route["risk_summary"]["miles"]["low"], 0)
            self.assertGreater(route["risk_summary"]["miles"]["unknown"], 0)
            for cp in route["checkpoints"]:
                self.assertEqual(cp["weather_status"], "unavailable")
                self.assertTrue(all(v is None for v in cp["weather"].values()))
                self.assertIsNone(cp["risk"]["combined"])
                self.assertTrue(cp["weather_missing_reason"])

    def test_observed_zero_weather_is_zero_and_low(self):
        self.weather.weather_fn = lambda c, h: HourlyRecord(0.0, 0.0, 0.0, 0.0)
        cp = self.ok()["routes"][0]["checkpoints"][1]
        self.assertEqual(cp["weather"]["rain_in_per_hr"], 0.0)
        self.assertEqual(cp["risk"]["combined"], "low")
        self.assertEqual(cp["weather_status"], "complete")

    def test_departure_beyond_the_forecast_horizon_is_flagged_not_extrapolated(self):
        body = {**VALID, "departure_datetime": "2026-12-25T08:00:00-05:00"}
        data = self.ok(body)
        self.assertEqual(data["recommendation"]["status"], STATUS_INSUFFICIENT_WEATHER)
        self.assertTrue(any("beyond the forecast horizon" in cp["weather_missing_reason"] for r in data["routes"] for cp in r["checkpoints"]))

    def test_partially_missing_wind_does_not_present_a_calm_checkpoint_as_fully_known(self):
        # Known limitation, pinned: a checkpoint missing only wind keeps its known (benign) rain/snow level,
        # but it is marked partial, the route is not "complete", and the status says so.
        self.weather.weather_fn = lambda c, h: HourlyRecord(None, None, 0.0, 0.0)
        data = self.ok()
        self.assertEqual(data["recommendation"]["status"], STATUS_RECOMMENDED_INCOMPLETE)
        cp = data["routes"][0]["checkpoints"][1]
        self.assertEqual(cp["weather_status"], "partial")
        self.assertIn("wind", cp["weather_missing_reason"])
        self.assertIsNone(cp["weather"]["wind_speed_mph"])
        self.assertFalse(data["routes"][0]["risk_summary"]["weather_data_complete"])
        self.assertIn("may be understated", data["recommendation"]["explanation"])

    def test_a_gappy_route_ranked_above_a_complete_one_is_disclosed(self):
        def weather(c, h):
            return None if h.hour == 18 and abs(c.lat - 33.0) < 0.5 else CALM

        self.weather.weather_fn = weather
        data = self.ok()
        routes = data["routes"]
        incomplete = [r for r in routes if not r["risk_summary"]["weather_data_complete"]]
        complete = [r for r in routes if r["risk_summary"]["weather_data_complete"]]
        if incomplete and complete and incomplete[0]["rank"] < complete[-1]["rank"]:
            self.assertTrue(any("may be understated" in n for n in data["method"]["notes"]))


class ResponseSchemaStabilityTests(ApiTestCase):
    ROUTE_KEYS = {
        "id", "source", "rank", "recommended", "eligible", "ineligible_reason", "distance_miles", "duration_seconds",
        "duration_text", "departure_datetime", "arrival_datetime", "geometry", "risk_summary", "ranking", "checkpoints",
    }
    CHECKPOINT_KEYS = {
        "index", "distance_miles", "segment_miles", "latitude", "longitude", "eta", "weather_status",
        "weather_missing_reason", "weather", "risk",
    }

    def test_schema_is_identical_for_complete_and_missing_weather(self):
        full = self.ok()
        self.weather.weather_fn = lambda c, h: None
        empty = self.ok()
        for data in (full, empty):
            self.assertEqual(set(data), {"api_version", "request", "units", "risk_levels", "recommendation", "method", "routes"})
            for route in data["routes"]:
                self.assertEqual(set(route), self.ROUTE_KEYS)
                self.assertEqual(set(route["risk_summary"]), set(full["routes"][0]["risk_summary"]))
                for cp in route["checkpoints"]:
                    self.assertEqual(set(cp), self.CHECKPOINT_KEYS)
                    self.assertEqual(set(cp["weather"]), set(full["routes"][0]["checkpoints"][0]["weather"]))
                    self.assertEqual(set(cp["risk"]), set(full["routes"][0]["checkpoints"][0]["risk"]))

    def test_geometry_is_longitude_first_and_matches_the_requested_endpoints(self):
        for route in self.ok()["routes"]:
            coords = route["geometry"]["coordinates"]
            self.assertEqual(route["geometry"]["type"], "LineString")
            lon0, lat0 = coords[0]
            lon1, lat1 = coords[-1]
            self.assertAlmostEqual((lat0, lon0), (VALID["origin"]["latitude"], VALID["origin"]["longitude"]), places=3)
            self.assertAlmostEqual((lat1, lon1), (VALID["destination"]["latitude"], VALID["destination"]["longitude"]), places=3)
            self.assertTrue(all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in coords))

    def test_checkpoint_coordinates_lie_on_their_routes_geometry(self):
        def distance_to_segment(p, a, b):
            (px, py), (ax, ay), (bx, by) = p, a, b
            dx, dy = bx - ax, by - ay
            t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5

        for route in self.ok()["routes"]:
            coords = route["geometry"]["coordinates"]
            for cp in route["checkpoints"]:
                point = (cp["longitude"], cp["latitude"])
                nearest = min(distance_to_segment(point, a, b) for a, b in zip(coords, coords[1:]))
                self.assertLess(nearest, 0.001, cp)  # degrees (~100 m): rounding only

    def test_equivalent_offsets_give_identical_assessments(self):
        a = self.ok({**VALID, "departure_datetime": "2026-10-14T08:00:00-05:00"})
        b = self.ok({**VALID, "departure_datetime": "2026-10-14T13:00:00Z"})
        c = self.ok({**VALID, "departure_datetime": "2026-10-14T18:30:00+05:30"})
        for other in (b, c):
            self.assertEqual(a["recommendation"], other["recommendation"])
            self.assertEqual(a["routes"], other["routes"])
        self.assertEqual(a["request"]["departure_datetime"], "2026-10-14T13:00:00Z")

    def test_response_contains_no_traceback_or_python_internals_on_failure(self):
        self.weather.error = RuntimeError("secret /path/to/file.py line 3")
        with self.assertLogs("trips.views", level="ERROR"):
            response = self.post()
        text = response.content.decode()
        self.assertEqual(response.status_code, 500)
        for needle in ("Traceback", "file.py", "RuntimeError", "secret"):
            self.assertNotIn(needle, text)


class SliderStyleBatchTests(BatchTestCase):
    """The 0-48 h slider asks for up to 12 departures at once; every result must equal a separate single request."""

    def departures(self, n=12, step_hours=4):
        start = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
        return [(start + timedelta(hours=step_hours * i)).isoformat().replace("+00:00", "Z") for i in range(n)]

    def test_twelve_departures_over_48_hours_match_single_requests_including_a_storm_and_data_gaps(self):
        def weather(c, h):
            if h.hour in (3, 4) and h.day == 15:
                return None  # data gap overnight
            if datetime(2026, 10, 15, 6, tzinfo=UTC) <= h <= datetime(2026, 10, 15, 14, tzinfo=UTC) and c.lon > -110:
                return wind(50.0)
            return CALM

        self.weather.weather_fn = weather
        departures = self.departures()
        batch = self.ok_batch(batch_payload(departures=departures))
        self.assertEqual(len(batch["results"]), 12)
        shared = {r["id"]: r for r in batch["routes"]}
        for departure, result in zip(departures, batch["results"]):
            with self.subTest(departure=departure):
                single = self.single(departure)
                self.assertTrue(result["ok"])
                self.assertEqual(result["recommendation"], single["recommendation"])
                self.assertEqual(result["notes"], single["method"]["notes"])
                self.assertEqual([without_geometry(r) for r in single["routes"]], result["routes"])
                for route in single["routes"]:
                    self.assertEqual(route["geometry"], shared[route["id"]]["geometry"])
                    self.assertEqual(route["distance_miles"], shared[route["id"]]["distance_miles"])

    def test_weather_is_reassessed_per_departure_not_relabelled(self):
        # The storm only covers the baseline route, so the recommendation may legitimately stay on a faster
        # via-route; what must change is the baseline's own risk as the departure moves out of the storm.
        def weather(c, h):
            on_baseline = abs(c.lat - straight_line_lat(c.lon)) < 0.1
            storm = datetime(2026, 10, 14, 20, tzinfo=UTC) <= h <= datetime(2026, 10, 15, 2, tzinfo=UTC)
            return wind(50.0) if on_baseline and storm and -110 < c.lon < -100 else CALM

        self.weather.weather_fn = weather
        data = self.ok_batch(batch_payload(departures=self.departures(12, 2)))
        blocked = []
        for result in data["results"]:
            baseline = next(r for r in result["routes"] if r["source"] == "baseline")
            blocked.append(baseline["risk_summary"]["no_travel_checkpoints"])
            self.assertEqual(baseline["eligible"], baseline["risk_summary"]["no_travel_checkpoints"] == 0)
        self.assertGreater(blocked[0], blocked[3])  # early departures hit the storm, later ones miss it
        self.assertEqual(blocked[3:], [0] * 9)
        self.assertEqual(blocked, sorted(blocked, reverse=True))

    def test_batch_sizes_one_and_twelve_succeed_and_thirteen_is_rejected(self):
        self.assertEqual(len(self.ok_batch(batch_payload(departures=self.departures(1)))["results"]), 1)
        self.assertEqual(len(self.ok_batch(batch_payload(departures=self.departures(12, 1)))["results"]), 12)
        too_many = self.post_batch(batch_payload(departures=self.departures(13, 1)))
        self.assertEqual(too_many.status_code, 400)

    def test_one_invalid_departure_rejects_the_whole_batch_before_any_provider_is_called(self):
        response = self.post_batch(batch_payload(departures=(self.departures(1)[0], "2026-10-14T20:00:00")))
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.routing.calls, self.weather.calls), ([], []))

    def test_results_keep_request_order_even_when_departures_are_unsorted(self):
        deps = list(reversed(self.departures(4)))
        data = self.ok_batch(batch_payload(departures=deps))
        self.assertEqual([r["departure_datetime"] for r in data["results"]], deps)
        self.assertEqual([r["index"] for r in data["results"]], [0, 1, 2, 3])

    def test_cached_and_uncached_plans_produce_the_same_assessment(self):
        caches["routes"].clear()
        miss = self.ok_batch()
        hit = self.ok_batch()
        self.assertEqual((miss["diagnostics"]["route_cache"], hit["diagnostics"]["route_cache"]), ("miss", "hit"))
        self.assertEqual(miss["routes"], hit["routes"])
        self.assertEqual(miss["results"], hit["results"])

    def test_a_cache_hit_still_fetches_fresh_weather(self):
        caches["routes"].clear()
        self.ok_batch()
        calls_after_first = len(self.weather.calls)
        self.ok_batch()
        self.assertGreater(len(self.weather.calls), calls_after_first)

    def test_batch_json_is_strict_and_free_of_nan(self):
        text = self.post_batch().content.decode()
        for token in ("NaN", "Infinity"):
            self.assertNotIn(token, text)
        json.loads(text)


class MethodAndContentTypeTests(ApiTestCase):
    def test_get_put_delete_are_405_on_both_endpoints_with_the_standard_error_shape(self):
        for url in (SINGLE_URL, BATCH_URL):
            for method in ("get", "put", "patch", "delete"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(strict_json(response)["error"]["code"], "method_not_allowed")

    def test_booleans_strings_and_non_finite_numbers_are_rejected_everywhere(self):
        bad_values = {
            "load_lb": [True, "42000", None, [], {}],
            "checkpoint_interval_miles": [True, "25", 25.5, 0, -25, None],
        }
        for field, values in bad_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.post({**VALID, field: value})
                    self.assertEqual(response.status_code, 400, response.content[:200])
        for literal in ("NaN", "Infinity", "-Infinity"):
            raw = json.dumps(VALID).replace("42000", literal)
            response = self.client.post(SINGLE_URL, raw, content_type="application/json")
            self.assertEqual(response.status_code, 400, literal)

    def test_load_bounds(self):
        for load, status in ((0.001, 200), (30_000, 200), (30_001, 200), (150_000, 200), (150_000.5, 400), (0, 400), (-1, 400)):
            with self.subTest(load=load):
                self.assertEqual(self.post({**VALID, "load_lb": load}).status_code, status)

    def test_datetime_formats(self):
        good = ["2026-10-14T08:00:00Z", "2026-10-14T08:00:00+00:00", "2026-10-14T08:00-05:00", "2026-10-14T08:00:00.123Z"]
        bad = ["2026-10-14T08:00:00", "2026-10-14", "08:00", "tomorrow", "", "2026-13-45T00:00:00Z", 1760000000, None, True]
        for value in good:
            with self.subTest(good=value):
                self.assertEqual(self.post({**VALID, "departure_datetime": value}).status_code, 200)
        for value in bad:
            with self.subTest(bad=value):
                self.assertEqual(self.post({**VALID, "departure_datetime": value}).status_code, 400)

    def test_coordinate_types_and_ranges(self):
        for lat, lon in ((True, 0), ("34", -118), (None, 0), (90.0001, 0), (-90.0001, 0), (0, 180.0001), (0, -180.0001)):
            with self.subTest(lat=lat, lon=lon):
                body = {**VALID, "origin": {"latitude": lat, "longitude": lon}}
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(self.post({**VALID, "origin": {**VALID["origin"], "extra": 1}}).status_code, 200)  # unknown keys are ignored

    def test_identical_and_near_identical_endpoints_are_rejected(self):
        self.assertEqual(self.post({**VALID, "destination": VALID["origin"]}).status_code, 400)
        close = {"latitude": VALID["origin"]["latitude"] + 0.0005, "longitude": VALID["origin"]["longitude"]}  # ~55 m
        self.assertEqual(self.post({**VALID, "destination": close}).status_code, 400)


class RankingExplanationTests(TestCase):
    def explain(self, a, b):
        from trips.presenters import _decisive
        from risk.aggregation import CheckpointRisk, summarize
        from trips.assessment import RouteAssessment

        def ra(segments, duration, index):
            summary = summarize([CheckpointRisk(lv, mi, lv is not None) for lv, mi in segments])
            route = Route(tuple(line_points(LOS_ANGELES, DALLAS)), 100 * MI, duration)
            return RouteAssessment(route, index, DEPARTURE, DEPARTURE, (), summary, index + 1, True, None, index == 0)

        return _decisive(ra(*a, 0), ra(*b, 1))

    def test_names_the_first_criterion_that_actually_differs(self):
        self.assertIn("fewer Severe miles", self.explain(([(L.LOW, 100)], 900), ([(L.SEVERE, 5), (L.LOW, 95)], 100)))
        self.assertIn("fewer High miles", self.explain(([(L.LOW, 100)], 900), ([(L.HIGH, 5), (L.LOW, 95)], 100)))
        self.assertIn("lower average risk", self.explain(([(L.LOW, 100)], 900), ([(L.MODERATE, 5), (L.LOW, 95)], 100)))
        self.assertIn("shorter travel time", self.explain(([(L.LOW, 100)], 100), ([(L.LOW, 100)], 900)))

    def test_incomplete_data_is_never_credited_as_the_reason_when_a_stated_criterion_decides(self):
        text = self.explain(([(L.LOW, 90), (None, 10)], 900), ([(L.SEVERE, 5), (L.LOW, 95)], 100))
        self.assertIn("fewer Severe miles", text)
        self.assertNotIn("complete weather data", text)

    def test_completeness_is_named_only_as_the_last_tie_break(self):
        text = self.explain(([(L.LOW, 100)], 100), ([(L.LOW, 90), (None, 10)], 100))
        self.assertIn("complete weather data", text)
        self.assertIn("equal", text)
