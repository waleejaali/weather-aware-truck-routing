"""Audit tests for weather retrieval and sampling (fake sessions only: nothing here touches the network)."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

import requests

from risk.levels import RiskLevel as L
from risk.thresholds import classify_rain_in_hr
from routing.types import Coordinate
from weather.errors import (
    WeatherConnectionError,
    WeatherRateLimitError,
    WeatherRequestError,
    WeatherResponseError,
    WeatherTimeoutError,
)
from weather.sampling import ceil_hour, floor_hour, sample_conditions
from weather.types import HourlyRecord, HourlySeries

from .test_open_meteo import END, HOURS, START, UNITS, FakeResponse, FakeSession, echo, entry, provider

UTC = timezone.utc
PLACE = Coordinate(34.05, -118.24)


def fetch_one(session, **kwargs):
    return provider(session, **kwargs).fetch_hourly([PLACE], START, END)[0]


class RainPlusShowersRoundingTests(TestCase):
    """Regression: float addition must not push an exact spec boundary to the wrong side."""

    def test_rain_plus_showers_summing_to_exactly_a_boundary_classifies_on_the_boundary(self):
        cases = [
            (0.01, 0.09, L.MODERATE),  # 0.01 + 0.09 == 0.09999999999999999 in binary floating point
            (0.09, 0.01, L.MODERATE),
            (0.05, 0.05, L.MODERATE),
            (0.10, 0.15, L.HIGH),
            (0.25, 0.25, L.SEVERE),
            (0.50, 0.50, L.SEVERE),
            (0.60, 0.40, L.SEVERE),  # exactly 1.00 stays Severe, not No Travel
            (0.70, 0.31, L.NO_TRAVEL),
        ]
        for rain, showers, expected in cases:
            with self.subTest(rain=rain, showers=showers):
                session = FakeSession(lambda p, r=rain, s=showers: FakeResponse(200, entry(rain=[r] * 3, showers=[s] * 3)))
                record = fetch_one(session).records[datetime.fromtimestamp(HOURS[1], tz=UTC)]
                self.assertEqual(classify_rain_in_hr(record.rain_in), expected, repr(record.rain_in))


class OpenMeteoUnitAndMetricTests(TestCase):
    def test_wind_gust_and_sustained_are_kept_apart(self):
        session = FakeSession(lambda p: FakeResponse(200, entry(wind_speed_10m=[11.0] * 3, wind_gusts_10m=[47.0] * 3)))
        record = fetch_one(session).records[datetime.fromtimestamp(HOURS[0], tz=UTC)]
        self.assertEqual((record.wind_speed_mph, record.wind_gust_mph), (11.0, 47.0))

    def test_every_non_expected_unit_is_refused(self):
        for variable, bad in [
            ("wind_speed_10m", "km/h"), ("wind_speed_10m", "m/s"), ("wind_gusts_10m", "kn"),
            ("rain", "mm"), ("showers", "mm"), ("snowfall", "cm"),
        ]:
            with self.subTest(variable=variable, unit=bad):
                units = {**UNITS, variable: bad}
                session = FakeSession(lambda p, u=units: FakeResponse(200, entry(units=u)))
                with self.assertRaises(WeatherResponseError):
                    fetch_one(session)

    def test_requested_units_are_imperial(self):
        session = FakeSession(echo)
        fetch_one(session)
        params = session.calls[0]["params"]
        self.assertEqual(params["wind_speed_unit"], "mph")
        self.assertEqual(params["precipitation_unit"], "inch")

    def test_snowfall_missing_stays_none_and_is_not_zero(self):
        session = FakeSession(lambda p: FakeResponse(200, entry(snowfall=[None] * 3)))
        record = fetch_one(session).records[datetime.fromtimestamp(HOURS[0], tz=UTC)]
        self.assertIsNone(record.snow_in)

    def test_observed_zero_is_zero_not_missing(self):
        session = FakeSession(lambda p: FakeResponse(200, entry(rain=[0] * 3, showers=[0] * 3, snowfall=[0] * 3)))
        record = fetch_one(session).records[datetime.fromtimestamp(HOURS[0], tz=UTC)]
        self.assertEqual((record.rain_in, record.snow_in), (0.0, 0.0))

    def test_non_finite_values_are_treated_as_missing(self):
        session = FakeSession(lambda p: FakeResponse(200, entry(wind_speed_10m=[float("nan")] * 3)))
        self.assertIsNone(fetch_one(session).records[datetime.fromtimestamp(HOURS[0], tz=UTC)].wind_speed_mph)


class OpenMeteoFailureMappingTests(TestCase):
    def test_http_failures_map_to_specific_errors(self):
        cases = [
            (429, WeatherRateLimitError),
            (400, WeatherRequestError),
            (500, WeatherRequestError),
            (502, WeatherRequestError),
            (503, WeatherRequestError),
            (504, WeatherRequestError),
        ]
        for status, error in cases:
            with self.subTest(status=status), self.assertRaises(error) as ctx:
                fetch_one(FakeSession(lambda p, s=status: FakeResponse(s, {"reason": "nope"})))
            if error is WeatherRequestError:
                self.assertEqual(ctx.exception.status_code, status)

    def test_transport_failures(self):
        for exc, error in [
            (requests.Timeout(), WeatherTimeoutError),
            (requests.ReadTimeout(), WeatherTimeoutError),
            (requests.ConnectionError(), WeatherConnectionError),
            (requests.TooManyRedirects(), WeatherConnectionError),
        ]:
            with self.subTest(exc=type(exc).__name__), self.assertRaises(error):
                fetch_one(FakeSession(exc=exc))

    def test_malformed_payloads(self):
        bad_payloads = {
            "not json": FakeResponse(200, bad_json=True),
            "empty object": FakeResponse(200, {}),
            "null": FakeResponse(200, None),
            "list for one location": FakeResponse(200, [entry(), entry()]),
            "hourly is a string": FakeResponse(200, {"hourly": "x", "hourly_units": UNITS}),
            "short column": FakeResponse(200, entry(rain=[0.0])),
            "string value": FakeResponse(200, entry(wind_speed_10m=["fast"] * 3)),
            "boolean value": FakeResponse(200, entry(snowfall=[True] * 3)),
            "string timestamp": FakeResponse(200, entry(times=["2026-10-14T00:00"] * 3)),
            "float timestamp": FakeResponse(200, entry(times=[1.5, 2.5, 3.5])),
        }
        for name, response in bad_payloads.items():
            with self.subTest(case=name), self.assertRaises(WeatherResponseError):
                fetch_one(FakeSession(lambda p, r=response: r))

    def test_error_messages_do_not_leak_request_urls_or_parameters(self):
        with self.assertRaises(WeatherRequestError) as ctx:
            fetch_one(FakeSession(lambda p: FakeResponse(500, {"reason": "boom"})))
        self.assertNotIn("latitude", str(ctx.exception))

    def test_a_failure_in_any_chunk_fails_the_whole_fetch(self):
        calls = []

        def responder(params):
            calls.append(params)
            return echo(params) if len(calls) == 1 else FakeResponse(429, {})

        locations = [Coordinate(30 + i * 0.1, -100.0) for i in range(60)]
        with self.assertRaises(WeatherRateLimitError):
            provider(FakeSession(responder), max_locations_per_request=50).fetch_hourly(locations, START, END)

    def test_empty_location_list_makes_no_request(self):
        session = FakeSession(echo)
        self.assertEqual(provider(session).fetch_hourly([], START, END), [])
        self.assertEqual(session.calls, [])

    def test_naive_or_inverted_windows_are_rejected_before_any_request(self):
        session = FakeSession(echo)
        with self.assertRaises(ValueError):
            provider(session).fetch_hourly([PLACE], datetime(2026, 10, 14), END)
        with self.assertRaises(ValueError):
            provider(session).fetch_hourly([PLACE], END, START)
        self.assertEqual(session.calls, [])

    def test_exactly_the_maximum_batch_size_is_a_single_request(self):
        session = FakeSession(echo)
        locations = [Coordinate(30 + i * 0.1, -100.0) for i in range(50)]
        provider(session, max_locations_per_request=50).fetch_hourly(locations, START, END)
        self.assertEqual(len(session.calls), 1)


H = datetime(2026, 10, 14, 10, tzinfo=UTC)


def record_series(**by_offset_hours):
    return HourlySeries(
        PLACE, {H + timedelta(hours=int(k[1:])): v for k, v in by_offset_hours.items()}
    )


class SamplingEdgeTests(TestCase):
    def test_exact_hour_uses_that_hours_instantaneous_wind_and_its_preceding_hour_precip(self):
        s = record_series(h0=HourlyRecord(30.0, 40.0, 0.2, 0.0), h1=HourlyRecord(10.0, 10.0, 0.0, 0.0))
        c = sample_conditions(s, H)
        self.assertEqual((c.wind_mph, c.gust_mph, c.rain_in_hr), (30.0, 40.0, 0.2))

    def test_just_after_the_hour_interpolates_wind_and_uses_next_hours_precip_window(self):
        s = record_series(h0=HourlyRecord(20.0, 0.0, 9.9, 0.0), h1=HourlyRecord(30.0, 45.0, 0.4, 1.5))
        c = sample_conditions(s, H + timedelta(seconds=1))
        self.assertAlmostEqual(c.wind_mph, 20.0, places=2)
        self.assertEqual((c.gust_mph, c.rain_in_hr, c.snow_in_hr), (45.0, 0.4, 1.5))

    def test_arrival_in_another_utc_offset_samples_the_same_instant(self):
        s = record_series(h0=HourlyRecord(33.0, 40.0, 0.1, 0.0), h1=HourlyRecord(33.0, 40.0, 0.1, 0.0))
        central = timezone(timedelta(hours=-5))
        self.assertEqual(sample_conditions(s, H.astimezone(central)), sample_conditions(s, H))

    def test_midnight_crossing(self):
        before = datetime(2026, 10, 14, 23, tzinfo=UTC)
        s = HourlySeries(
            PLACE,
            {
                before: HourlyRecord(10.0, 0.0, 0.0, 0.0),
                before + timedelta(hours=1): HourlyRecord(30.0, 0.0, 0.2, 0.0),
            },
        )
        c = sample_conditions(s, datetime(2026, 10, 14, 23, 30, tzinfo=UTC))
        self.assertAlmostEqual(c.wind_mph, 20.0)
        self.assertEqual(c.rain_in_hr, 0.2)  # taken from the 00:00 record on the next UTC day
        self.assertEqual(floor_hour(datetime(2026, 10, 15, 0, 0, tzinfo=UTC)), before + timedelta(hours=1))

    def test_naive_arrival_is_rejected(self):
        with self.assertRaises(ValueError):
            sample_conditions(record_series(), datetime(2026, 10, 14, 10, 30))

    def test_hour_missing_on_either_side_makes_wind_unknown_not_extrapolated(self):
        only_lower = record_series(h0=HourlyRecord(50.0, 0.0, 0.0, 0.0))
        c = sample_conditions(only_lower, H + timedelta(minutes=30))
        self.assertIsNone(c.wind_mph)
        self.assertIn("wind", c.missing)
        only_upper = record_series(h1=HourlyRecord(50.0, 0.0, 0.0, 0.0))
        self.assertIsNone(sample_conditions(only_upper, H + timedelta(minutes=30)).wind_mph)

    def test_empty_series_reports_everything_missing(self):
        c = sample_conditions(record_series(), H)
        self.assertEqual(c.missing, ("wind", "gust", "rain", "snow"))

    def test_sustained_and_gust_are_never_mixed(self):
        s = record_series(h0=HourlyRecord(12.0, 60.0, 0.0, 0.0), h1=HourlyRecord(12.0, 60.0, 0.0, 0.0))
        c = sample_conditions(s, H)
        self.assertEqual(c.wind_mph, 12.0)
        self.assertEqual(c.gust_mph, 60.0)

    def test_ceil_hour_never_returns_a_past_time(self):
        for minute in (0, 1, 59):
            t = H + timedelta(minutes=minute)
            self.assertGreaterEqual(ceil_hour(t), t)
            self.assertLessEqual(floor_hour(t), t)

    def test_dst_offsets_do_not_move_utc_sampling(self):
        # 2026-11-01 01:30 US Eastern happens twice; as UTC instants they are an hour apart.
        first = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
        second = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
        self.assertEqual(ceil_hour(second) - ceil_hour(first), timedelta(hours=1))
