from datetime import datetime, timezone
from unittest import TestCase

import requests

from routing.types import Coordinate
from weather.errors import (
    WeatherConnectionError,
    WeatherRateLimitError,
    WeatherRequestError,
    WeatherResponseError,
    WeatherTimeoutError,
)
from weather.providers.open_meteo import OpenMeteoProvider

UTC = timezone.utc
T0 = int(datetime(2026, 10, 14, 0, tzinfo=UTC).timestamp())
HOURS = [T0 + 3600 * i for i in range(3)]
START, END = datetime(2026, 10, 14, 0, tzinfo=UTC), datetime(2026, 10, 14, 2, tzinfo=UTC)
UNITS = {
    "time": "unixtime", "wind_speed_10m": "mp/h", "wind_gusts_10m": "mp/h",
    "rain": "inch", "showers": "inch", "snowfall": "inch",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code, self._payload, self._bad = status_code, payload, bad_json

    def json(self):
        if self._bad:
            raise ValueError("bad json")
        return self._payload


def entry(times=HOURS, lat=34.05, lon=-118.24, units=UNITS, **overrides):
    n = len(times)
    hourly = {
        "time": list(times),
        "wind_speed_10m": [10.0] * n, "wind_gusts_10m": [20.0] * n,
        "rain": [0.01] * n, "showers": [0.02] * n, "snowfall": [0.3] * n,
    }
    hourly.update(overrides)
    return {"latitude": lat, "longitude": lon, "hourly_units": units, "hourly": hourly}


class FakeSession:
    def __init__(self, responder=None, exc=None):
        self.responder, self.exc, self.calls = responder, exc, []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.responder(params)


def echo(params, **entry_kwargs):
    # Open-Meteo returns a bare object for one location and a list for several
    entries = [entry(lat=float(a), lon=float(b), **entry_kwargs)
               for a, b in zip(params["latitude"].split(","), params["longitude"].split(","))]
    return FakeResponse(200, entries if len(entries) > 1 else entries[0])


def provider(session, **kwargs):
    return OpenMeteoProvider(session=session, **kwargs)


class OpenMeteoSuccessTests(TestCase):
    def test_single_location_object_response_and_normalised_values(self):
        session = FakeSession(echo)
        [series] = provider(session).fetch_hourly([Coordinate(34.05, -118.24)], START, END)
        record = series.records[datetime(2026, 10, 14, 1, tzinfo=UTC)]
        self.assertEqual(sorted(series.records), [datetime.fromtimestamp(h, tz=UTC) for h in HOURS])
        self.assertEqual((record.wind_speed_mph, record.wind_gust_mph), (10.0, 20.0))
        self.assertAlmostEqual(record.rain_in, 0.03)
        self.assertEqual(record.snow_in, 0.3)
        self.assertEqual(series.grid, Coordinate(34.05, -118.24))

    def test_request_parameters(self):
        session = FakeSession(echo)
        provider(session, base_url="https://example.test/", timeout_s=7).fetch_hourly(
            [Coordinate(34.05, -118.24)], START, END
        )
        call = session.calls[0]
        p = call["params"]
        self.assertEqual(call["url"], "https://example.test/v1/forecast")
        self.assertEqual(call["timeout"], 7)
        self.assertEqual((p["wind_speed_unit"], p["precipitation_unit"], p["timeformat"]), ("mph", "inch", "unixtime"))
        self.assertEqual((p["start_date"], p["end_date"], p["timezone"]), ("2026-10-14", "2026-10-14", "GMT"))
        self.assertEqual(p["hourly"].split(","), ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"])
        self.assertNotIn("precipitation", p["hourly"].split(","))  # it folds in snow water equivalent

    def test_dates_follow_utc_window(self):
        session = FakeSession(echo)
        end = datetime(2026, 10, 15, 3, tzinfo=UTC)
        provider(session).fetch_hourly([Coordinate(34, -118)], START, end)
        self.assertEqual(session.calls[0]["params"]["end_date"], "2026-10-15")

    def test_many_locations_are_batched_not_one_request_each(self):
        session = FakeSession(echo)
        locations = [Coordinate(30 + i * 0.1, -100.0) for i in range(120)]
        result = provider(session, max_locations_per_request=50).fetch_hourly(locations, START, END)
        self.assertEqual(len(result), 120)
        self.assertEqual([len(c["params"]["latitude"].split(",")) for c in session.calls], [50, 50, 20])
        self.assertEqual([s.requested for s in result], locations)

    def test_duplicate_locations_are_requested_once_but_returned_for_each(self):
        session = FakeSession(echo)
        a, b = Coordinate(34.0522, -118.2437), Coordinate(34.0524, -118.2439)  # same ~1 km cell
        c = Coordinate(35.0, -100.0)
        result = provider(session).fetch_hourly([a, c, b], START, END)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(len(session.calls[0]["params"]["latitude"].split(",")), 2)
        self.assertEqual([s.requested for s in result], [a, c, b])
        self.assertEqual(result[0].records, result[2].records)

    def test_null_values_become_none_and_missing_hours_are_absent(self):
        times = [HOURS[0], HOURS[2]]
        session = FakeSession(lambda p: FakeResponse(200, entry(times, wind_speed_10m=[None, 12.0], showers=[None, 0.0])))
        [series] = provider(session).fetch_hourly([Coordinate(34, -118)], START, END)
        self.assertNotIn(datetime(2026, 10, 14, 1, tzinfo=UTC), series.records)
        first = series.records[datetime(2026, 10, 14, 0, tzinfo=UTC)]
        self.assertIsNone(first.wind_speed_mph)
        self.assertIsNone(first.rain_in)
        self.assertEqual(first.snow_in, 0.3)

    def test_available_window(self):
        start, end = provider(FakeSession()).available_window(datetime(2026, 10, 12, 15, 30, tzinfo=UTC))
        self.assertEqual(start, datetime(2026, 7, 12, tzinfo=UTC))
        self.assertEqual(end, datetime(2026, 10, 28, tzinfo=UTC))

    def test_attribution_present(self):
        a = provider(FakeSession()).attribution
        self.assertIn("Open-Meteo", a.text)
        self.assertEqual(a.license, "CC BY 4.0")


class OpenMeteoFailureTests(TestCase):
    def fetch(self, session):
        return provider(session).fetch_hourly([Coordinate(34, -118)], START, END)

    def test_http_errors(self):
        with self.assertRaises(WeatherRateLimitError):
            self.fetch(FakeSession(lambda p: FakeResponse(429, {})))
        with self.assertRaisesRegex(WeatherRequestError, "out of allowed range") as ctx:
            self.fetch(FakeSession(lambda p: FakeResponse(400, {"error": True, "reason": "Parameter 'start_date' is out of allowed range"})))
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(WeatherRequestError):
            self.fetch(FakeSession(lambda p: FakeResponse(500, None)))

    def test_network_errors(self):
        with self.assertRaises(WeatherTimeoutError):
            self.fetch(FakeSession(exc=requests.Timeout()))
        with self.assertRaises(WeatherConnectionError):
            self.fetch(FakeSession(exc=requests.ConnectionError()))

    def test_malformed_payloads(self):
        bad = {
            "not json": FakeResponse(200, bad_json=True),
            "no hourly": FakeResponse(200, {"latitude": 1}),
            "length mismatch": FakeResponse(200, entry(snowfall=[0.0])),
            "string value": FakeResponse(200, entry(snowfall=["lots", 0, 0])),
            "bad timestamp": FakeResponse(200, entry(times=["2026-10-14T00:00"] * 3)),
            "location count": FakeResponse(200, [entry(), entry()]),
        }
        for name, response in bad.items():
            with self.subTest(name), self.assertRaises(WeatherResponseError):
                self.fetch(FakeSession(lambda p, r=response: r))

    def test_unexpected_units_are_rejected_rather_than_misread(self):
        for variable, wrong in (("wind_speed_10m", "km/h"), ("snowfall", "cm"), ("rain", "mm")):
            with self.subTest(variable):
                units = {**UNITS, variable: wrong}
                with self.assertRaisesRegex(WeatherResponseError, variable):
                    self.fetch(FakeSession(lambda p, u=units: FakeResponse(200, entry(units=u))))

    def test_invalid_window_arguments(self):
        p = provider(FakeSession(echo))
        with self.assertRaises(ValueError):
            p.fetch_hourly([Coordinate(1, 1)], datetime(2026, 10, 14), END)
        with self.assertRaises(ValueError):
            p.fetch_hourly([Coordinate(1, 1)], END, START)
