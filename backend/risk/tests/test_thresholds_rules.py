from unittest import TestCase

from risk.levels import RiskLevel as L
from risk.rules import assess_conditions, load_override
from risk.thresholds import classify_rain_in_hr, classify_snow_in_hr, classify_wind_mph


class ThresholdBoundaryTests(TestCase):
    def check(self, fn, cases):
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(fn(value), expected)

    def test_wind(self):
        self.check(classify_wind_mph, [
            (0, L.LOW), (24.99, L.LOW), (25, L.MODERATE), (34.99, L.MODERATE), (35, L.HIGH),
            (44.99, L.HIGH), (45, L.SEVERE), (54.99, L.SEVERE), (55, L.NO_TRAVEL), (90, L.NO_TRAVEL),
        ])

    def test_rain(self):
        self.check(classify_rain_in_hr, [
            (0, L.LOW), (0.0999, L.LOW), (0.10, L.MODERATE), (0.2499, L.MODERATE), (0.25, L.HIGH),
            (0.4999, L.HIGH), (0.50, L.SEVERE), (1.00, L.SEVERE), (1.0001, L.NO_TRAVEL),
        ])

    def test_snow(self):
        self.check(classify_snow_in_hr, [
            (0, L.LOW), (0.4999, L.LOW), (0.5, L.MODERATE), (0.9999, L.MODERATE), (1.0, L.HIGH),
            (1.9999, L.HIGH), (2.0, L.SEVERE), (3.0, L.SEVERE), (3.0001, L.NO_TRAVEL),
        ])

    def test_invalid_inputs_rejected(self):
        for fn in (classify_wind_mph, classify_rain_in_hr, classify_snow_in_hr):
            for bad in (-0.1, float("nan")):
                with self.subTest(fn=fn.__name__, bad=bad), self.assertRaises(ValueError):
                    fn(bad)


class LoadRuleTests(TestCase):
    def test_override_boundaries(self):
        cases = [
            # (wind, load, expected override)
            (34.99, 100_000, None),            # below 35 mph: load irrelevant
            (35, 40_000, None),                # load must be strictly above 40,000
            (35, 40_001, L.SEVERE),
            (44.99, 40_001, L.SEVERE),
            (44.99, 40_000, None),
            (45, 30_000, None),                # strictly above 30,000
            (45, 30_001, L.NO_TRAVEL),
            (54.99, 30_001, L.NO_TRAVEL),
            (54.99, 30_000, None),
            (60, 0, None),                     # >=55 is handled by the wind band, not a load rule
        ]
        for wind, load, expected in cases:
            with self.subTest(wind=wind, load=load):
                self.assertEqual(load_override(wind, load), expected)

    def test_wind_55_is_no_travel_for_any_load(self):
        for load in (0, 1_000, 80_000):
            self.assertEqual(self.assess(wind=55, load=load).level, L.NO_TRAVEL)

    def test_heavy_load_at_45_to_55_is_no_travel_light_load_is_severe(self):
        self.assertEqual(self.assess(wind=50, load=30_001).level, L.NO_TRAVEL)
        self.assertEqual(self.assess(wind=50, load=30_000).level, L.SEVERE)

    def test_heavy_load_at_35_to_45_is_severe_otherwise_high(self):
        self.assertEqual(self.assess(wind=40, load=40_001).level, L.SEVERE)
        self.assertEqual(self.assess(wind=40, load=40_000).level, L.HIGH)

    @staticmethod
    def assess(*, wind, load, rain=0.0, snow=0.0):
        return assess_conditions(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=load)


class PrecedenceTests(TestCase):
    def test_highest_of_all_hazards_and_override_wins(self):
        r = assess_conditions(wind_mph=20, rain_in_hr=0.3, snow_in_hr=2.5, load_lb=10_000)
        self.assertEqual((r.wind_level, r.rain_level, r.snow_level, r.level), (L.LOW, L.HIGH, L.SEVERE, L.SEVERE))

    def test_override_raises_but_never_lowers(self):
        # Rain alone is No Travel; a Severe load override must not lower it.
        r = assess_conditions(wind_mph=40, rain_in_hr=1.5, snow_in_hr=0, load_lb=50_000)
        self.assertEqual(r.load_override, L.SEVERE)
        self.assertEqual(r.level, L.NO_TRAVEL)

    def test_override_raises_over_lower_hazards(self):
        r = assess_conditions(wind_mph=40, rain_in_hr=0.05, snow_in_hr=0, load_lb=50_000)
        self.assertEqual((r.wind_level, r.level), (L.HIGH, L.SEVERE))
        self.assertTrue(any("load" in reason for reason in r.reasons))

    def test_missing_values_are_skipped_not_assumed_zero(self):
        r = assess_conditions(wind_mph=None, rain_in_hr=0.3, snow_in_hr=None, load_lb=0)
        self.assertEqual(r.level, L.HIGH)
        self.assertIsNone(r.wind_level)

    def test_no_data_at_all_gives_no_level(self):
        self.assertIsNone(assess_conditions(wind_mph=None, rain_in_hr=None, snow_in_hr=None, load_lb=0).level)

    def test_negative_load_rejected(self):
        with self.assertRaises(ValueError):
            assess_conditions(wind_mph=1, rain_in_hr=0, snow_in_hr=0, load_lb=-1)
