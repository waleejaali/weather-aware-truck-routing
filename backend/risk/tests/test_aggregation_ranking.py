from unittest import TestCase

from risk.aggregation import CheckpointRisk, summarize
from risk.levels import RiskLevel as L
from risk.ranking import rank_routes


def cp(level, miles, complete=True):
    return CheckpointRisk(level, miles, complete)


def summary(*pairs, complete=True):
    return summarize([cp(level, miles, complete) for level, miles in pairs])


class AggregationTests(TestCase):
    def test_miles_by_level_and_mileage_weighted_average(self):
        s = summary((L.LOW, 60), (L.HIGH, 20), (L.SEVERE, 20))
        self.assertEqual((s.miles(L.LOW), s.miles(L.HIGH), s.miles(L.SEVERE), s.miles(L.MODERATE)), (60, 20, 20, 0))
        # (0*60 + 2*20 + 3*20) / 100
        self.assertAlmostEqual(s.average_score, 1.0)
        self.assertEqual((s.known_miles, s.unknown_miles, s.total_miles), (100, 0, 100))
        self.assertEqual(s.max_level, L.SEVERE)
        self.assertTrue(s.data_complete and not s.has_no_travel)

    def test_no_travel_scores_four_and_is_counted(self):
        s = summary((L.NO_TRAVEL, 10), (L.LOW, 30))
        self.assertAlmostEqual(s.average_score, 1.0)
        self.assertTrue(s.has_no_travel)
        self.assertEqual(s.no_travel_checkpoints, 1)

    def test_coverage_is_known_share_of_miles(self):
        self.assertAlmostEqual(summary((L.LOW, 30), (None, 70)).coverage, 0.3)
        self.assertEqual(summarize([]).coverage, 0.0)

    def test_unknown_miles_are_excluded_from_average_not_counted_low(self):
        s = summary((L.HIGH, 50), (None, 50), complete=True)
        self.assertEqual((s.known_miles, s.unknown_miles), (50, 50))
        self.assertAlmostEqual(s.average_score, 2.0)

    def test_incomplete_flag_and_all_unknown(self):
        self.assertFalse(summarize([cp(L.LOW, 10, complete=False)]).data_complete)
        s = summary((None, 10), complete=False)
        self.assertIsNone(s.average_score)
        self.assertIsNone(s.max_level)


class RankingTests(TestCase):
    def rank(self, summaries, durations=None):
        return rank_routes(summaries, durations or [3600.0] * len(summaries))

    def test_fewest_severe_miles_beats_everything_below_it(self):
        a = summary((L.SEVERE, 5), (L.LOW, 95))
        b = summary((L.SEVERE, 1), (L.HIGH, 99))
        self.assertEqual(self.rank([a, b], [100, 9999]).order, (1, 0))

    def test_then_fewest_high_miles(self):
        a = summary((L.HIGH, 10), (L.LOW, 90))
        b = summary((L.HIGH, 5), (L.MODERATE, 95))
        self.assertEqual(self.rank([a, b], [100, 9999]).order, (1, 0))

    def test_then_lowest_average_risk(self):
        a = summary((L.MODERATE, 50), (L.LOW, 50))
        b = summary((L.MODERATE, 10), (L.LOW, 90))
        self.assertEqual(self.rank([a, b], [100, 9999]).order, (1, 0))

    def test_then_shortest_travel_time(self):
        a = summary((L.LOW, 100))
        b = summary((L.LOW, 100))
        self.assertEqual(self.rank([a, b], [5000, 4000]).order, (1, 0))

    def test_float_noise_does_not_break_ties(self):
        a = summary((L.SEVERE, 10.0), (L.LOW, 90))
        b = summary((L.SEVERE, 10.0000001), (L.LOW, 90))
        self.assertEqual(self.rank([a, b], [5000, 4000]).order, (1, 0))

    def test_no_travel_route_is_never_recommended_even_if_best_otherwise(self):
        risky = summary((L.NO_TRAVEL, 1), (L.LOW, 99))
        severe = summary((L.SEVERE, 100))
        r = self.rank([risky, severe], [100, 9999])
        self.assertEqual(r.eligible, (False, True))
        self.assertEqual((r.order, r.recommended), ((1, 0), 1))

    def test_all_no_travel_means_no_recommendation(self):
        a = summary((L.NO_TRAVEL, 20), (L.LOW, 80))
        b = summary((L.NO_TRAVEL, 5), (L.LOW, 95))
        r = self.rank([a, b])
        self.assertIsNone(r.recommended)
        self.assertEqual(r.order, (1, 0))  # order still matters for display

    def test_complete_data_ranks_ahead_of_gaps(self):
        clean = summary((L.MODERATE, 100))
        gappy = summary((L.LOW, 50), (None, 50), complete=False)
        r = self.rank([gappy, clean], [100, 9999])
        self.assertEqual(r.recommended, 1)

    def test_coverage_threshold_boundary(self):
        eighty = summary((L.LOW, 80), (None, 20), complete=False)
        seventy_nine = summary((L.LOW, 79), (None, 21), complete=False)
        self.assertEqual(self.rank([eighty, seventy_nine]).eligible, (True, False))
        self.assertEqual(rank_routes([seventy_nine], [1.0], min_coverage=0.5).eligible, (True,))

    def test_route_with_no_weather_is_never_recommended(self):
        nothing = summary((None, 100), complete=False)
        r = self.rank([nothing])
        self.assertIsNone(r.recommended)
        self.assertEqual(nothing.coverage, 0.0)

    def test_unknown_route_does_not_beat_a_known_risky_one(self):
        nothing = summary((None, 100), complete=False)
        risky = summary((L.SEVERE, 50), (L.LOW, 50))
        r = self.rank([nothing, risky], [100, 9999])
        self.assertEqual((r.order, r.recommended), ((1, 0), 1))

    def test_invalid_min_coverage_rejected(self):
        with self.assertRaises(ValueError):
            rank_routes([summary((L.LOW, 1))], [1.0], min_coverage=1.1)

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            rank_routes([summary((L.LOW, 1))], [1.0, 2.0])
