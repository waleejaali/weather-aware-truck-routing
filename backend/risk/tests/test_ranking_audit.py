"""Audit tests for the recommendation order.

Assignment: (1) fewest Severe miles, (2) fewest High miles, (3) lowest average risk, (4) shortest travel time.

Eligibility is a gate separate from ranking: routes with a No Travel checkpoint, or with weather for < 80% of their
miles, are never recommended. Among eligible routes the order is exactly the four criteria above. The one addition is a
final tie-breaker: if all four tie, complete weather data beats gaps. `DataCompletenessPolicyTests` pins that it can
never override a stated criterion.
"""

from unittest import TestCase

from risk.aggregation import CheckpointRisk, summarize
from risk.levels import RiskLevel as L
from risk.ranking import rank_routes

U = None  # unknown level


def route(*segments, complete=True):
    """Build a summary from (level, miles) pairs. Unknown (None) segments are incomplete automatically."""
    return summarize([CheckpointRisk(level, miles, complete and level is not None) for level, miles in segments])


def rank(routes, durations=None, **kw):
    durations = durations or [3600.0 * (i + 1) for i in range(len(routes))]
    return rank_routes(routes, durations, **kw)


class LexicographicOrderTests(TestCase):
    def test_fewer_severe_miles_beat_fewer_high_miles_and_shorter_time(self):
        a = route((L.SEVERE, 10), (L.LOW, 90))  # 10 severe, 0 high
        b = route((L.HIGH, 90), (L.LOW, 10))  # 0 severe, 90 high -> still wins
        r = rank([a, b], [1000, 99_999])
        self.assertEqual(r.recommended, 1)
        self.assertEqual(r.order, (1, 0))

    def test_fewer_severe_miles_win_even_when_much_slower_and_riskier_on_average(self):
        a = route((L.SEVERE, 1), (L.LOW, 99))
        b = route((L.HIGH, 100))  # average 2.0 vs 0.03, slower
        self.assertEqual(rank([a, b], [100, 200_000]).recommended, 1)

    def test_severe_tie_falls_to_fewer_high_miles_despite_average_and_time(self):
        a = route((L.HIGH, 10), (L.LOW, 90))  # avg 0.2, fast
        b = route((L.MODERATE, 100))  # 0 high, avg 1.0 (worse), slow
        self.assertEqual(rank([a, b], [100, 200_000]).recommended, 1)

    def test_severe_and_high_tie_falls_to_lower_average_despite_time(self):
        a = route((L.MODERATE, 100))  # avg 1.0, fast
        b = route((L.MODERATE, 20), (L.LOW, 80))  # avg 0.2, slow
        self.assertEqual(rank([a, b], [100, 200_000]).recommended, 1)

    def test_first_three_tie_falls_to_shortest_time(self):
        a = route((L.MODERATE, 50), (L.LOW, 50))
        b = route((L.MODERATE, 50), (L.LOW, 50))
        self.assertEqual(rank([a, b], [5000, 4000]).recommended, 1)
        self.assertEqual(rank([a, b], [4000, 5000]).recommended, 0)

    def test_a_blended_score_would_disagree_with_the_lexicographic_choice(self):
        # Guard against anyone replacing the order with a weighted sum: lots of High never beats one Severe mile.
        a = route((L.SEVERE, 0.5), (L.LOW, 99.5))
        b = route((L.HIGH, 100))
        self.assertLess(a.average_score, b.average_score)  # a is better on average AND time...
        self.assertEqual(rank([a, b], [100, 50]).recommended, 1)  # ...but loses on the first criterion

    def test_exact_ties_keep_input_order_which_is_fastest_first_from_the_planner(self):
        same = route((L.LOW, 100))
        r = rank([same, same, same], [100, 100, 100])
        self.assertEqual(r.order, (0, 1, 2))
        self.assertEqual(r.recommended, 0)

    def test_ranking_is_independent_of_input_order(self):
        a = route((L.SEVERE, 5), (L.LOW, 95))
        b = route((L.HIGH, 30), (L.LOW, 70))
        c = route((L.MODERATE, 100))
        durations = {"a": 100, "b": 200, "c": 300}
        base = rank([a, b, c], [durations["a"], durations["b"], durations["c"]])
        shuffled = rank([c, a, b], [durations["c"], durations["a"], durations["b"]])
        self.assertEqual(base.order[0], 2)  # c: no severe, no high
        self.assertEqual(shuffled.order[0], 0)  # same route, now first in the input

    def test_a_shorter_distance_route_can_lose_to_a_longer_one(self):
        # Distance is not a ranking criterion; only risk and time are.
        short_but_risky = route((L.HIGH, 20), (L.LOW, 80))
        long_but_clear = route((L.LOW, 150))
        self.assertEqual(rank([short_but_risky, long_but_clear], [3000, 9000]).recommended, 1)

    def test_float_noise_below_the_rounding_precision_does_not_decide_a_tie(self):
        a = route((L.SEVERE, 10.000001), (L.LOW, 90))
        b = route((L.SEVERE, 10.0), (L.LOW, 90))
        self.assertEqual(rank([a, b], [200, 100]).recommended, 1)  # tie on severe miles -> duration decides


class EligibilityTests(TestCase):
    def test_a_no_travel_route_is_never_recommended_even_if_it_is_the_best_on_paper(self):
        blocked = route((L.NO_TRAVEL, 1), (L.LOW, 99))
        severe = route((L.SEVERE, 100))
        r = rank([blocked, severe], [100, 999])
        self.assertEqual(r.eligible, (False, True))
        self.assertEqual(r.recommended, 1)

    def test_all_routes_blocked_means_no_recommendation_but_still_an_order(self):
        r = rank([route((L.NO_TRAVEL, 10), (L.LOW, 90)), route((L.NO_TRAVEL, 50), (L.LOW, 50))])
        self.assertIsNone(r.recommended)
        self.assertEqual(r.eligible, (False, False))
        self.assertEqual(r.order, (0, 1))  # less No Travel mileage listed first, but not recommended

    def test_no_travel_with_zero_miles_still_makes_a_route_ineligible(self):
        zero_length = route((L.NO_TRAVEL, 0.0), (L.LOW, 100))
        self.assertTrue(zero_length.has_no_travel)
        self.assertFalse(rank([zero_length]).eligible[0])

    def test_eligible_routes_always_rank_ahead_of_ineligible_ones(self):
        blocked = route((L.NO_TRAVEL, 1), (L.LOW, 99))
        ok = route((L.SEVERE, 100))
        r = rank([blocked, ok])
        self.assertEqual(r.order, (1, 0))

    def test_empty_input_is_not_an_error(self):
        r = rank_routes([], [])
        self.assertEqual((r.order, r.eligible, r.recommended), ((), (), None))

    def test_mismatched_lengths_and_bad_coverage_are_rejected(self):
        with self.assertRaises(ValueError):
            rank_routes([route((L.LOW, 1))], [])
        for bad in (-0.1, 1.1):
            with self.assertRaises(ValueError):
                rank_routes([route((L.LOW, 1))], [1.0], min_coverage=bad)

    def test_single_route_is_recommended_when_eligible(self):
        self.assertEqual(rank([route((L.SEVERE, 100))]).recommended, 0)


class CoverageThresholdTests(TestCase):
    def test_exactly_80_percent_coverage_qualifies(self):
        r = rank([route((L.LOW, 80), (U, 20))])
        self.assertTrue(r.eligible[0])
        self.assertEqual(r.recommended, 0)

    def test_just_under_80_percent_does_not(self):
        r = rank([route((L.LOW, 79.99), (U, 20.01))])
        self.assertFalse(r.eligible[0])
        self.assertIsNone(r.recommended)

    def test_exactly_80_percent_with_float_unfriendly_segment_lengths_still_qualifies(self):
        # Regression: 0.3 * 4 known / (0.3 * 5 total) evaluates to 0.7999999999999999 in binary floating point.
        s = route(*([(L.LOW, 0.3)] * 4 + [(U, 0.3)]))
        self.assertTrue(rank([s]).eligible[0])
        self.assertTrue(rank([s]).recommended == 0)

    def test_custom_threshold_is_respected_at_the_edge(self):
        s = route((L.LOW, 50), (U, 50))
        self.assertTrue(rank([s], min_coverage=0.5).eligible[0])
        self.assertFalse(rank([s], min_coverage=0.51).eligible[0])

    def test_no_known_weather_at_all_is_ineligible_and_has_no_average(self):
        s = route((U, 100))
        self.assertEqual((s.coverage, s.average_score, s.max_level), (0.0, None, None))
        self.assertFalse(rank([s]).eligible[0])

    def test_zero_length_route_does_not_divide_by_zero(self):
        s = route((L.LOW, 0.0))
        self.assertEqual(s.coverage, 0.0)
        self.assertIsNone(s.average_score)
        self.assertFalse(rank([s]).eligible[0])

    def test_unknown_miles_are_never_counted_as_low(self):
        s = route((L.HIGH, 10), (U, 90))
        self.assertEqual(s.miles(L.LOW), 0)
        self.assertEqual(s.unknown_miles, 90)
        self.assertEqual(s.average_score, 2.0)  # known miles only, not diluted by the unknown 90


class AggregationConsistencyTests(TestCase):
    def test_known_plus_unknown_equals_total_and_levels_sum_to_known(self):
        s = route((L.LOW, 12.5), (L.MODERATE, 7.25), (L.HIGH, 3), (L.SEVERE, 1.5), (L.NO_TRAVEL, 0.75), (U, 5))
        self.assertAlmostEqual(sum(s.miles_by_level.values()), s.known_miles)
        self.assertAlmostEqual(s.known_miles + s.unknown_miles, s.total_miles)
        self.assertAlmostEqual(s.total_miles, 30.0)

    def test_average_is_mileage_weighted(self):
        s = route((L.LOW, 75), (L.SEVERE, 25))  # 0*75 + 3*25 over 100
        self.assertAlmostEqual(s.average_score, 0.75)

    def test_average_counts_no_travel_as_the_worst_score(self):
        self.assertAlmostEqual(route((L.NO_TRAVEL, 10)).average_score, 4.0)

    def test_max_level_ignores_unknown(self):
        self.assertEqual(route((L.MODERATE, 1), (U, 5)).max_level, L.MODERATE)

    def test_data_complete_is_false_if_any_checkpoint_is_incomplete(self):
        self.assertFalse(route((L.LOW, 1), (L.LOW, 1), complete=False).data_complete)
        self.assertTrue(route((L.LOW, 1), (L.LOW, 1)).data_complete)


class DataCompletenessPolicyTests(TestCase):
    """Completeness is only a last tie-breaker; it never outranks Severe miles, High miles, average risk or time."""

    def test_incomplete_but_sufficient_route_with_fewer_severe_miles_beats_a_complete_route(self):
        gappy_but_calm = route((L.LOW, 85), (U, 15))  # eligible: 85% coverage, 0 severe
        complete_but_severe = route((L.SEVERE, 10), (L.LOW, 90))
        r = rank([gappy_but_calm, complete_but_severe], [999, 100])
        self.assertTrue(all(r.eligible))
        self.assertEqual(r.recommended, 0)

    def test_fewer_high_miles_average_risk_and_time_each_beat_completeness(self):
        complete_a = route((L.HIGH, 10), (L.LOW, 90))
        gappy_fewer_high = route((L.LOW, 85), (U, 15))
        self.assertEqual(rank([complete_a, gappy_fewer_high], [100, 999]).recommended, 1)

        complete_b = route((L.MODERATE, 50), (L.LOW, 50))
        gappy_lower_avg = route((L.MODERATE, 10), (L.LOW, 80), (U, 10))
        self.assertEqual(rank([complete_b, gappy_lower_avg], [100, 999]).recommended, 1)

        complete_c = route((L.LOW, 100))
        gappy_faster = route((L.LOW, 90), (U, 10))
        self.assertEqual(rank([complete_c, gappy_faster], [500, 100]).recommended, 1)

    def test_complete_data_breaks_an_exact_tie_on_all_four_criteria(self):
        gappy = route((L.LOW, 90), (U, 10))
        complete = route((L.LOW, 100))
        self.assertEqual(rank([gappy, complete], [100, 100]).recommended, 1)

    def test_remaining_exact_ties_keep_input_order(self):
        a, b = route((L.LOW, 100)), route((L.LOW, 100))
        self.assertEqual(rank([a, b], [100, 100]).order, (0, 1))

    def test_ineligible_gappy_route_is_still_excluded(self):
        too_gappy = route((L.LOW, 70), (U, 30))
        self.assertFalse(rank([too_gappy]).eligible[0])
        self.assertIsNone(rank([too_gappy]).recommended)

    def test_unknown_miles_are_not_counted_as_low_in_the_average(self):
        self.assertEqual(route((L.HIGH, 10), (U, 90)).miles(L.LOW), 0)
