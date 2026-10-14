"""Audit tests: every threshold in the assignment, checked literally (below / at / above each edge).

Assignment bands, read as half-open [lower, upper) except where the spec's wording says otherwise:
  wind  mph    : Low <25, Moderate 25-34, High 35-44, Severe 45-54, No Travel >=55
  rain  in/hr  : Low <0.10, Moderate 0.10-0.25, High 0.25-0.50, Severe 0.50-1.00, No Travel >1.00
  snow  in/hr  : Low <0.5, Moderate 0.5-1.0, High 1.0-2.0, Severe 2.0-3.0, No Travel >3.0

Rain/snow adjacent bands share an edge in the spec (0.25 appears in Moderate and High). The code treats the
shared edge as the *higher* band, the conservative reading, and Severe's upper edge (1.00 / 3.0) as Severe
because the spec says No Travel is strictly "greater than". These tests pin that interpretation.
"""

from unittest import TestCase

from risk.levels import RiskLevel as L
from risk.rules import assess_conditions, load_override
from risk.thresholds import classify_rain_in_hr, classify_snow_in_hr, classify_wind_mph

TINY = 1e-6

WIND_CASES = [
    (0, L.LOW), (24.9, L.LOW), (24.999999, L.LOW),
    (25, L.MODERATE), (25.000001, L.MODERATE), (34, L.MODERATE), (34.9, L.MODERATE), (34.999999, L.MODERATE),
    (35, L.HIGH), (35.000001, L.HIGH), (44, L.HIGH), (44.9, L.HIGH), (44.999999, L.HIGH),
    (45, L.SEVERE), (45.000001, L.SEVERE), (54, L.SEVERE), (54.9, L.SEVERE), (54.999999, L.SEVERE),
    (55, L.NO_TRAVEL), (55.000001, L.NO_TRAVEL), (80, L.NO_TRAVEL), (200, L.NO_TRAVEL),
]
RAIN_CASES = [
    (0, L.LOW), (0.09, L.LOW), (0.099999, L.LOW),
    (0.10, L.MODERATE), (0.100001, L.MODERATE), (0.24, L.MODERATE), (0.249999, L.MODERATE),
    (0.25, L.HIGH), (0.250001, L.HIGH), (0.49, L.HIGH), (0.499999, L.HIGH),
    (0.50, L.SEVERE), (0.500001, L.SEVERE), (0.99, L.SEVERE), (0.999999, L.SEVERE),
    (1.00, L.SEVERE),  # spec: only values GREATER than 1.00 are No Travel
    (1.000001, L.NO_TRAVEL), (1.01, L.NO_TRAVEL), (5, L.NO_TRAVEL),
]
SNOW_CASES = [
    (0, L.LOW), (0.4, L.LOW), (0.499999, L.LOW),
    (0.5, L.MODERATE), (0.500001, L.MODERATE), (0.99, L.MODERATE), (0.999999, L.MODERATE),
    (1.0, L.HIGH), (1.000001, L.HIGH), (1.99, L.HIGH), (1.999999, L.HIGH),
    (2.0, L.SEVERE), (2.000001, L.SEVERE), (2.99, L.SEVERE), (2.999999, L.SEVERE),
    (3.0, L.SEVERE),  # spec: only values GREATER than 3.0 are No Travel
    (3.000001, L.NO_TRAVEL), (3.01, L.NO_TRAVEL), (10, L.NO_TRAVEL),
]


class ThresholdBoundaryTests(TestCase):
    def test_wind_bands(self):
        for value, expected in WIND_CASES:
            with self.subTest(wind_mph=value):
                self.assertEqual(classify_wind_mph(value), expected)

    def test_rain_bands(self):
        for value, expected in RAIN_CASES:
            with self.subTest(rain_in_hr=value):
                self.assertEqual(classify_rain_in_hr(value), expected)

    def test_snow_bands(self):
        for value, expected in SNOW_CASES:
            with self.subTest(snow_in_hr=value):
                self.assertEqual(classify_snow_in_hr(value), expected)

    def test_integer_inputs_behave_like_floats(self):
        self.assertEqual(classify_rain_in_hr(1), L.SEVERE)
        self.assertEqual(classify_snow_in_hr(3), L.SEVERE)
        self.assertEqual(classify_wind_mph(55), L.NO_TRAVEL)

    def test_invalid_values_are_rejected_not_classified(self):
        for fn in (classify_wind_mph, classify_rain_in_hr, classify_snow_in_hr):
            for bad in (-0.001, float("nan"), None, "5"):
                with self.subTest(fn=fn.__name__, value=bad), self.assertRaises(ValueError):
                    fn(bad)

    def test_infinity_is_no_travel_not_an_error(self):
        # inf cannot come from the providers (non-finite values are mapped to None) but must not crash or read as safe.
        for fn in (classify_wind_mph, classify_rain_in_hr, classify_snow_in_hr):
            self.assertEqual(fn(float("inf")), L.NO_TRAVEL)


LOAD_OVERRIDE_CASES = [
    # (wind, load, expected override)
    (55, 0.01, None),  # >=55 is No Travel from the wind band itself, for any load (see test below)
    (54.999999, 30_000, None),
    (54.999999, 30_000.01, L.NO_TRAVEL),
    (45, 30_000, None),  # strictly greater than 30,000 is required
    (45, 30_000.01, L.NO_TRAVEL),
    (45, 30_001, L.NO_TRAVEL),
    (45, 80_000, L.NO_TRAVEL),
    (44.999999, 150_000, L.SEVERE),  # just under 45 falls in the 35-44 rule
    (44.999999, 40_000, None),
    (44.999999, 40_000.01, L.SEVERE),
    (35, 40_000, None),  # strictly greater than 40,000 is required
    (35, 40_000.01, L.SEVERE),
    (35, 40_001, L.SEVERE),
    (34.999999, 150_000, None),
    (25, 150_000, None),
    (0, 150_000, None),
]


class LoadOverrideTests(TestCase):
    def test_override_table(self):
        for wind, load, expected in LOAD_OVERRIDE_CASES:
            with self.subTest(wind=wind, load=load):
                self.assertEqual(load_override(wind, load), expected)

    def test_wind_55_is_no_travel_for_every_load(self):
        for load in (0, 1, 10_000, 30_000, 30_001, 40_000, 40_001, 80_000, 150_000):
            for wind in (55, 55.5, 70):
                with self.subTest(load=load, wind=wind):
                    risk = assess_conditions(wind_mph=wind, rain_in_hr=0.0, snow_in_hr=0.0, load_lb=load)
                    self.assertEqual(risk.level, L.NO_TRAVEL)

    def test_resulting_level_for_each_wind_band_and_load(self):
        table = [
            # wind, load, expected combined level
            (45, 30_000, L.SEVERE), (45, 30_001, L.NO_TRAVEL),
            (54.9, 30_000, L.SEVERE), (54.9, 30_001, L.NO_TRAVEL),
            (35, 40_000, L.HIGH), (35, 40_001, L.SEVERE),
            (44.9, 40_000, L.HIGH), (44.9, 40_001, L.SEVERE),
            # in the 45-54 band a load between 30,000 and 40,000 still escalates to No Travel
            (50, 35_000, L.NO_TRAVEL),
            (30, 150_000, L.MODERATE), (10, 150_000, L.LOW),
        ]
        for wind, load, expected in table:
            with self.subTest(wind=wind, load=load):
                risk = assess_conditions(wind_mph=wind, rain_in_hr=0.0, snow_in_hr=0.0, load_lb=load)
                self.assertEqual(risk.level, expected)

    def test_a_load_override_never_lowers_a_worse_hazard(self):
        # wind 35-44 + heavy load => Severe, but 1.5 in/hr rain is No Travel and must win
        risk = assess_conditions(wind_mph=40, rain_in_hr=1.5, snow_in_hr=0.0, load_lb=60_000)
        self.assertEqual(risk.level, L.NO_TRAVEL)
        self.assertEqual(risk.load_override, L.SEVERE)

    def test_a_load_override_raises_a_milder_hazard(self):
        risk = assess_conditions(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0.0, load_lb=60_000)
        self.assertEqual(risk.level, L.SEVERE)  # rain alone is only High

    def test_negative_load_rejected(self):
        with self.assertRaises(ValueError):
            assess_conditions(wind_mph=10, rain_in_hr=0, snow_in_hr=0, load_lb=-1)


class CombinedHazardTests(TestCase):
    def test_worst_hazard_wins(self):
        cases = [
            ((10, 0.0, 0.0), L.LOW),
            ((30, 0.0, 0.0), L.MODERATE),
            ((10, 0.3, 0.0), L.HIGH),
            ((10, 0.0, 2.5), L.SEVERE),
            ((30, 0.3, 2.5), L.SEVERE),
            ((60, 0.0, 0.0), L.NO_TRAVEL),
            ((10, 1.01, 0.0), L.NO_TRAVEL),
            ((10, 0.0, 3.01), L.NO_TRAVEL),
            ((10, 1.0, 3.0), L.SEVERE),
        ]
        for (wind, rain, snow), expected in cases:
            with self.subTest(wind=wind, rain=rain, snow=snow):
                self.assertEqual(
                    assess_conditions(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=10_000).level, expected
                )

    def test_individual_levels_are_reported_per_hazard(self):
        r = assess_conditions(wind_mph=30, rain_in_hr=0.3, snow_in_hr=2.5, load_lb=10_000)
        self.assertEqual((r.wind_level, r.rain_level, r.snow_level), (L.MODERATE, L.HIGH, L.SEVERE))
        self.assertIsNone(r.load_override)

    def test_missing_measurements_are_unknown_not_low(self):
        r = assess_conditions(wind_mph=None, rain_in_hr=None, snow_in_hr=None, load_lb=10_000)
        self.assertIsNone(r.level)
        self.assertEqual((r.wind_level, r.rain_level, r.snow_level), (None, None, None))

    def test_partial_data_uses_only_known_hazards_and_still_flags_danger(self):
        self.assertEqual(
            assess_conditions(wind_mph=60, rain_in_hr=None, snow_in_hr=None, load_lb=1).level, L.NO_TRAVEL
        )
        self.assertEqual(
            assess_conditions(wind_mph=None, rain_in_hr=None, snow_in_hr=2.5, load_lb=1).level, L.SEVERE
        )

    def test_missing_wind_means_no_load_override(self):
        r = assess_conditions(wind_mph=None, rain_in_hr=0.0, snow_in_hr=0.0, load_lb=150_000)
        self.assertIsNone(r.load_override)
        self.assertEqual(r.level, L.LOW)  # known measurements only; the caller marks the checkpoint incomplete


class RiskLevelOrderTests(TestCase):
    def test_order_and_scores(self):
        self.assertEqual([int(x) for x in (L.LOW, L.MODERATE, L.HIGH, L.SEVERE, L.NO_TRAVEL)], [0, 1, 2, 3, 4])
        self.assertEqual([x.label for x in L], ["Low", "Moderate", "High", "Severe", "No Travel"])
