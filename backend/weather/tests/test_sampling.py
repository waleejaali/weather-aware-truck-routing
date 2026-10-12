from datetime import datetime, timedelta, timezone
from unittest import TestCase

from routing.types import Coordinate
from weather.sampling import ceil_hour, floor_hour, sample_conditions
from weather.types import HourlyRecord, HourlySeries

UTC = timezone.utc
H10 = datetime(2026, 10, 14, 10, tzinfo=UTC)


def rec(wind=None, gust=None, rain=None, snow=None):
    return HourlyRecord(wind, gust, rain, snow)


def series(**by_hour):
    """series(h10=rec(...), h11=rec(...)) keyed by hour of day on 2026-10-14."""
    records = {datetime(2026, 10, 14, int(k[1:]), tzinfo=UTC): v for k, v in by_hour.items()}
    return HourlySeries(Coordinate(34, -118), records)


class HourHelperTests(TestCase):
    def test_floor_and_ceil(self):
        t = datetime(2026, 10, 14, 10, 20, tzinfo=UTC)
        self.assertEqual((floor_hour(t), ceil_hour(t)), (H10, H10 + timedelta(hours=1)))
        self.assertEqual((floor_hour(H10), ceil_hour(H10)), (H10, H10))

    def test_other_timezones_are_converted_to_utc(self):
        central = timezone(timedelta(hours=-5))
        self.assertEqual(floor_hour(datetime(2026, 10, 14, 5, 30, tzinfo=central)), H10)


class SamplingTests(TestCase):
    def test_wind_is_interpolated_between_surrounding_hours(self):
        s = series(h10=rec(wind=20.0), h11=rec(wind=40.0))
        c = sample_conditions(s, datetime(2026, 10, 14, 10, 15, tzinfo=UTC))
        self.assertAlmostEqual(c.wind_mph, 25.0)

    def test_precip_and_gust_use_the_hour_ending_after_arrival(self):
        s = series(
            h10=rec(rain=0.9, snow=0.9, gust=90.0),
            h11=rec(rain=0.2, snow=0.6, gust=33.0),
        )
        c = sample_conditions(s, datetime(2026, 10, 14, 10, 15, tzinfo=UTC))
        # 10:15 lies inside the hour ending 11:00, not the one ending 10:00.
        self.assertEqual((c.rain_in_hr, c.snow_in_hr, c.gust_mph), (0.2, 0.6, 33.0))

    def test_arrival_exactly_on_the_hour_uses_that_hours_record(self):
        s = series(h10=rec(wind=30.0, gust=50.0, rain=0.1, snow=0.0), h11=rec(wind=99.0, gust=99.0, rain=9.0, snow=9.0))
        c = sample_conditions(s, H10)
        self.assertEqual((c.wind_mph, c.gust_mph, c.rain_in_hr, c.snow_in_hr), (30.0, 50.0, 0.1, 0.0))
        self.assertEqual(c.missing, ())

    def test_missing_record_is_reported_never_substituted(self):
        s = series(h10=rec(wind=20.0, gust=20.0, rain=0.0, snow=0.0))  # nothing for 11:00
        c = sample_conditions(s, datetime(2026, 10, 14, 10, 30, tzinfo=UTC))
        self.assertIsNone(c.wind_mph)
        self.assertEqual(c.missing, ("wind", "gust", "rain", "snow"))

    def test_missing_field_in_an_existing_record(self):
        s = series(h10=rec(wind=20.0), h11=rec(wind=20.0, gust=25.0, rain=None, snow=0.0))
        c = sample_conditions(s, datetime(2026, 10, 14, 10, 30, tzinfo=UTC))
        self.assertEqual((c.wind_mph, c.missing), (20.0, ("rain",)))

    def test_wind_needs_both_neighbours_unless_on_the_hour(self):
        s = series(h10=rec(wind=20.0))
        self.assertIsNone(sample_conditions(s, datetime(2026, 10, 14, 10, 30, tzinfo=UTC)).wind_mph)
        self.assertEqual(sample_conditions(s, H10).wind_mph, 20.0)

    def test_naive_arrival_rejected(self):
        with self.assertRaises(ValueError):
            sample_conditions(series(), datetime(2026, 10, 14, 10))
