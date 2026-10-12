"""Orchestration tests: fake weather provider, synthetic routes, no HTTP."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

from risk.levels import RiskLevel as L
from routing.checkpoints import METERS_PER_MILE
from routing.tests.factories import DALLAS, LOS_ANGELES, line_points, make_route
from routing.types import Route
from trips.assessment import (
    STATUS_INSUFFICIENT_WEATHER,
    STATUS_NO_SAFE_ROUTE,
    STATUS_RECOMMENDED,
    STATUS_RECOMMENDED_INCOMPLETE,
    assess_routes,
)
from weather.errors import WeatherTimeoutError
from weather.providers.base import WeatherProvider
from weather.sampling import ceil_hour, floor_hour
from weather.types import Attribution, HourlyRecord, HourlySeries

UTC = timezone.utc
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
DEPARTURE = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
CALM = HourlyRecord(5.0, 10.0, 0.0, 0.0)
ATTRIBUTION = Attribution("Weather data by Fake", "https://fake.test", "CC BY 4.0", "https://fake.test/license")
MILE = METERS_PER_MILE


class FakeWeatherProvider(WeatherProvider):
    name = "fake"
    attribution = ATTRIBUTION

    def __init__(self, weather_fn=lambda coordinate, hour: CALM, error=None):
        self.weather_fn, self.error, self.calls = weather_fn, error, []

    def available_window(self, now):
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=92), today + timedelta(days=16)

    def fetch_hourly(self, locations, start, end):
        self.calls.append((list(locations), start, end))
        if self.error:
            raise self.error
        hours = []
        t = start.replace(hour=0)
        while t <= end.replace(hour=23):
            hours.append(t)
            t += timedelta(hours=1)
        return [
            HourlySeries(c, {h: record for h in hours if (record := self.weather_fn(c, h)) is not None})
            for c in locations
        ]


def assess(routes, provider=None, **overrides):
    kwargs = dict(departure=DEPARTURE, load_lb=20_000, interval_miles=50, now=NOW)
    kwargs.update(overrides)
    return assess_routes(routes, provider=provider or FakeWeatherProvider(), **kwargs)


def wind(mph, **extra):
    return HourlyRecord(mph, extra.get("gust", mph), extra.get("rain", 0.0), extra.get("snow", 0.0))


class WeatherAtArrivalTests(TestCase):
    def setUp(self):
        # 200 mi in 10 h; checkpoints every 50 mi arrive 2.5 h apart.
        self.route = Route(tuple(line_points(LOS_ANGELES, DALLAS)), 200 * MILE, 10 * 3600.0)

    def test_each_checkpoint_uses_the_weather_at_its_own_arrival_time(self):
        # A storm only after 14:00 UTC; departure 08:00 UTC is calm.
        storm_start = DEPARTURE + timedelta(hours=6)
        provider = FakeWeatherProvider(lambda c, h: wind(60.0) if h >= storm_start else CALM)
        trip = assess([self.route], provider)
        levels = [cp.level for cp in trip.routes[0].checkpoints]
        etas = [cp.eta for cp in trip.routes[0].checkpoints]
        for eta, hours in zip(etas, (0, 2.5, 5, 7.5, 10)):
            self.assertLess(abs(eta - (DEPARTURE + timedelta(hours=hours))), timedelta(seconds=1))
        # Wind interpolates, so the 5.0 h checkpoint (13:00) is calm and the 7.5 h one (15:30) is stormy.
        self.assertEqual(levels[:3], [L.LOW, L.LOW, L.LOW])
        self.assertEqual(levels[3:], [L.NO_TRAVEL, L.NO_TRAVEL])
        self.assertTrue(trip.routes[0].summary.has_no_travel)

    def test_departure_time_weather_is_not_applied_to_every_checkpoint(self):
        provider = FakeWeatherProvider(lambda c, h: wind(60.0) if h == floor_hour(DEPARTURE) else CALM)
        trip = assess([self.route], provider)
        levels = [cp.level for cp in trip.routes[0].checkpoints]
        self.assertEqual(levels[0], L.NO_TRAVEL)
        self.assertNotIn(L.NO_TRAVEL, levels[1:])

    def test_departure_in_another_timezone_is_converted(self):
        central = timezone(timedelta(hours=-5))
        trip = assess([self.route], departure=datetime(2026, 10, 14, 3, 0, tzinfo=central))  # == 08:00 UTC
        self.assertEqual(trip.routes[0].departure, DEPARTURE)
        self.assertEqual(trip.routes[0].checkpoints[0].eta, DEPARTURE)

    def test_weather_is_fetched_in_one_batched_call_covering_all_arrival_hours(self):
        provider = FakeWeatherProvider()
        trip = assess([self.route, make_route(LOS_ANGELES, DALLAS, 0.2)], provider)
        self.assertEqual(len(provider.calls), 1)
        locations, start, end = provider.calls[0]
        self.assertEqual(len(locations), sum(len(r.checkpoints) for r in trip.routes))
        self.assertEqual(start, floor_hour(DEPARTURE))
        self.assertGreaterEqual(end, ceil_hour(trip.routes[0].arrival))

    def test_wind_metric_selects_gust_or_sustained(self):
        provider = FakeWeatherProvider(lambda c, h: HourlyRecord(20.0, 60.0, 0.0, 0.0))
        self.assertEqual(assess([self.route], provider).routes[0].summary.max_level, L.LOW)
        self.assertEqual(assess([self.route], provider, wind_metric="gust").routes[0].summary.max_level, L.NO_TRAVEL)

    def test_load_rules_flow_through(self):
        provider = FakeWeatherProvider(lambda c, h: wind(40.0))
        self.assertEqual(assess([self.route], provider, load_lb=45_000).routes[0].summary.max_level, L.SEVERE)
        self.assertEqual(assess([self.route], provider, load_lb=35_000).routes[0].summary.max_level, L.HIGH)


class UnavailableWeatherTests(TestCase):
    def setUp(self):
        self.route = Route(tuple(line_points(LOS_ANGELES, DALLAS)), 200 * MILE, 10 * 3600.0)

    def test_arrival_beyond_forecast_horizon_is_unavailable_and_never_fetched(self):
        provider = FakeWeatherProvider(lambda c, h: wind(60.0))
        trip = assess([self.route], provider, departure=NOW + timedelta(days=30))
        self.assertEqual(provider.calls, [])
        for cp in trip.routes[0].checkpoints:
            self.assertIsNone(cp.level)
            self.assertIsNone(cp.conditions)
            self.assertIn("beyond the forecast horizon", cp.unavailable_reason)
        self.assertEqual(trip.routes[0].summary.unknown_miles, 200)
        # No weather at all: nothing can be called safe, so there is no recommendation.
        self.assertEqual(trip.status, STATUS_INSUFFICIENT_WEATHER)
        self.assertIsNone(trip.recommended)
        self.assertFalse(trip.routes[0].eligible)
        self.assertIn("0%", trip.routes[0].ineligible_reason)
        self.assertTrue(any("outside" in n for n in trip.notes))

    def test_departure_before_available_history_is_unavailable(self):
        trip = assess([self.route], departure=NOW - timedelta(days=200))
        self.assertIn("before the available history", trip.routes[0].checkpoints[0].unavailable_reason)

    def test_trip_crossing_the_horizon_is_partially_known(self):
        provider = FakeWeatherProvider()
        # The window ends 16 days after today's midnight; depart 5 h before it (ETAs 19:00, 21:30, then past the end).
        departure = NOW.replace(hour=0) + timedelta(days=16) - timedelta(hours=5)
        trip = assess([self.route], provider, departure=departure)
        known = [cp.level is not None for cp in trip.routes[0].checkpoints]
        self.assertEqual(known, [True, True, False, False, False])
        self.assertFalse(trip.routes[0].summary.data_complete)
        self.assertEqual(len(provider.calls[0][0]), 2)  # only servable checkpoints were requested

    def test_missing_hours_leave_checkpoints_unknown_without_substitution(self):
        # ETAs 08:00, 10:30, 13:00, 15:30, 18:00. 13:00 needs the 13:00 record; 15:30 needs 15:00 and 16:00.
        provider = FakeWeatherProvider(lambda c, h: None if h.hour in (13, 16) else wind(10.0))
        trip = assess([self.route], provider)
        cps = trip.routes[0].checkpoints
        self.assertEqual([cp.level is None for cp in cps], [False, False, True, True, False])
        self.assertIn("data for the hour of arrival", cps[2].unavailable_reason)
        self.assertFalse(trip.routes[0].summary.data_complete)

    def test_partial_fields_keep_the_hazards_that_are_known(self):
        provider = FakeWeatherProvider(lambda c, h: HourlyRecord(60.0, 60.0, None, 0.0))
        cp = assess([self.route], provider).routes[0].checkpoints[1]
        self.assertEqual(cp.level, L.NO_TRAVEL)  # wind alone is enough
        self.assertFalse(cp.complete)
        self.assertIn("rain", cp.unavailable_reason)

    def test_provider_failure_propagates(self):
        with self.assertRaises(WeatherTimeoutError):
            assess([self.route], FakeWeatherProvider(error=WeatherTimeoutError("slow")))


class RecommendationTests(TestCase):
    def setUp(self):
        self.straight = make_route(LOS_ANGELES, DALLAS)
        self.north = make_route(LOS_ANGELES, DALLAS, 0.5)
        self.south = make_route(LOS_ANGELES, DALLAS, -0.5)

    @staticmethod
    def straight_line_lat(lon):
        return LOS_ANGELES.lat + (DALLAS.lat - LOS_ANGELES.lat) * (lon - LOS_ANGELES.lon) / (DALLAS.lon - LOS_ANGELES.lon)

    def storm_on_straight_route(self, c, h):
        on_straight = abs(c.lat - self.straight_line_lat(c.lon)) < 0.1 and -110 < c.lon < -100
        return wind(50.0) if on_straight else CALM  # Severe for a light load

    def test_route_avoiding_the_storm_wins_over_the_faster_one(self):
        trip = assess([self.straight, self.north, self.south], FakeWeatherProvider(self.storm_on_straight_route))
        by_plan = {r.plan_index: r for r in trip.routes}
        self.assertGreater(by_plan[0].summary.miles(L.SEVERE), 0)
        self.assertEqual(by_plan[1].summary.miles(L.SEVERE), 0)
        self.assertEqual(trip.routes[-1].plan_index, 0)  # straight route ranked last
        self.assertIn(trip.recommended.plan_index, (1, 2))
        self.assertEqual(trip.status, STATUS_RECOMMENDED)
        self.assertEqual([r.rank for r in trip.routes], [1, 2, 3])
        self.assertEqual([r.recommended for r in trip.routes], [True, False, False])

    def test_equal_weather_recommends_the_fastest_route(self):
        routes = [self.north, self.straight, self.south]
        trip = assess(routes)
        fastest = min(range(3), key=lambda i: routes[i].duration_s)
        self.assertEqual(trip.recommended.plan_index, fastest)

    def test_no_travel_route_is_excluded_even_when_fastest(self):
        provider = FakeWeatherProvider(lambda c, h: wind(60.0) if self.storm_on_straight_route(c, h).wind_speed_mph > 40 else CALM)
        trip = assess([self.straight, self.north, self.south], provider)
        straight = next(r for r in trip.routes if r.plan_index == 0)
        self.assertFalse(straight.eligible)
        self.assertTrue(straight.no_travel_checkpoints)
        self.assertNotEqual(trip.recommended.plan_index, 0)

    def test_every_route_no_travel_gives_no_recommendation(self):
        trip = assess([self.straight, self.north], FakeWeatherProvider(lambda c, h: wind(60.0)))
        self.assertIsNone(trip.recommended)
        self.assertEqual(trip.status, STATUS_NO_SAFE_ROUTE)
        self.assertFalse(any(r.recommended or r.eligible for r in trip.routes))
        self.assertTrue(any("No Travel" in n for n in trip.notes))

    def missing_in_band(self, lon_min, lon_max):
        def weather(c, h):  # weather is missing along the (faster) straight route only
            on_straight = abs(c.lat - self.straight_line_lat(c.lon)) < 0.1 and lon_min < c.lon < lon_max
            return None if on_straight else CALM

        return FakeWeatherProvider(weather)

    def test_route_with_too_little_weather_is_not_recommended_even_if_fastest(self):
        trip = assess([self.straight, self.north], self.missing_in_band(-110, -100))  # ~half the route unknown
        straight = next(r for r in trip.routes if r.plan_index == 0)
        self.assertFalse(straight.eligible)
        self.assertIn("only", straight.ineligible_reason)
        self.assertEqual(trip.recommended.plan_index, 1)
        self.assertEqual(trip.status, STATUS_RECOMMENDED)
        self.assertTrue(any("Route 1 cannot be recommended" in n for n in trip.notes))

    def test_small_gap_keeps_route_eligible_but_ranks_it_after_complete_routes(self):
        trip = assess([self.straight, self.north], self.missing_in_band(-102, -100))  # a few % unknown
        straight = next(r for r in trip.routes if r.plan_index == 0)
        self.assertTrue(straight.eligible)
        self.assertFalse(straight.summary.data_complete)
        self.assertGreater(straight.weather_coverage, 0.8)
        self.assertEqual(trip.recommended.plan_index, 1)  # slower, but its weather is fully known
        self.assertTrue(any("ranked after" in n for n in trip.notes))

    def test_only_route_with_a_small_gap_is_recommended_with_an_explicit_warning(self):
        trip = assess([self.straight], self.missing_in_band(-102, -100))
        self.assertEqual(trip.status, STATUS_RECOMMENDED_INCOMPLETE)
        self.assertEqual(trip.recommended.plan_index, 0)

    def test_no_travel_plus_insufficient_data_is_insufficient_not_no_safe_route(self):
        def weather(c, h):
            if c.lat > self.straight_line_lat(c.lon) + 0.2:  # north route: no data at all in the middle
                return None
            on_straight = abs(c.lat - self.straight_line_lat(c.lon)) < 0.1 and -110 < c.lon < -100
            return wind(60.0) if on_straight else CALM

        trip = assess([self.straight, self.north], FakeWeatherProvider(weather), min_weather_coverage=0.99)
        self.assertEqual(trip.status, STATUS_INSUFFICIENT_WEATHER)
        self.assertIsNone(trip.recommended)

    def test_coverage_threshold_is_configurable(self):
        provider = self.missing_in_band(-110, -100)
        self.assertIsNone(assess([self.straight], provider).recommended)
        self.assertIsNotNone(assess([self.straight], provider, min_weather_coverage=0.0).recommended)

    def test_result_carries_attribution_and_parameters(self):
        trip = assess([self.straight], interval_miles=25, load_lb=12_345)
        self.assertEqual(trip.attribution, ATTRIBUTION)
        self.assertEqual((trip.interval_miles, trip.load_lb, trip.wind_metric), (25, 12_345, "sustained"))
        self.assertEqual(trip.min_weather_coverage, 0.8)

    def test_assumptions_state_method_limits_and_the_wind_metric_used(self):
        text = " ".join(assess([self.straight], interval_miles=25).assumptions)
        self.assertIn("every 25 miles", text)
        self.assertIn("hazards between checkpoints can be missed", text)
        self.assertIn("estimates", text)
        self.assertIn("sustained 10 m wind speed", text)
        self.assertIn("gusts are not used", text)
        gust_text = " ".join(assess([self.straight], wind_metric="gust").assumptions)
        self.assertIn("sustained speed is not used", gust_text)

    def test_wind_value_used_matches_the_chosen_metric_and_is_never_mixed(self):
        provider = FakeWeatherProvider(lambda c, h: HourlyRecord(20.0, 50.0, 0.0, 0.0))
        sustained = assess([self.straight], provider).routes[0].checkpoints[1]
        gust = assess([self.straight], provider, wind_metric="gust").routes[0].checkpoints[1]
        self.assertEqual((sustained.wind_mph_used, sustained.level), (20.0, L.LOW))
        self.assertEqual((gust.wind_mph_used, gust.level), (50.0, L.SEVERE))


class InputValidationTests(TestCase):
    def setUp(self):
        self.route = make_route(LOS_ANGELES, DALLAS)

    def test_rejects_bad_inputs(self):
        cases = [
            dict(routes=[]),
            dict(departure=datetime(2026, 10, 14, 8)),
            dict(now=datetime(2026, 10, 12)),
            dict(interval_miles=30),
            dict(wind_metric="average"),
            dict(load_lb=-1),
            dict(min_weather_coverage=1.5),
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                routes = overrides.pop("routes", [self.route])
                assess(routes, **overrides)

    def test_all_three_documented_intervals_work(self):
        counts = {i: len(assess([self.route], interval_miles=i).routes[0].checkpoints) for i in (10, 25, 50)}
        self.assertLess(counts[50], counts[25])
        self.assertLess(counts[25], counts[10])
