from datetime import datetime, timedelta, timezone
from unittest import TestCase

from routing.checkpoints import METERS_PER_MILE, checkpoint_distances_m, estimate_arrival, sample_checkpoints
from routing.geometry import haversine_m, points_at_distances
from routing.types import Route

from .factories import DALLAS, LOS_ANGELES, line_points, make_route

MILE = METERS_PER_MILE
DEPARTURE = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)


def miles(values):
    return [round(v / MILE, 3) for v in values]


class CheckpointDistanceTests(TestCase):
    def test_regular_spacing_start_and_end_included(self):
        self.assertEqual(miles(checkpoint_distances_m(110 * MILE, 25)), [0, 25, 50, 75, 100, 110])

    def test_checkpoint_near_the_end_is_dropped_not_duplicated(self):
        # 100 mi is only 0.3 mi short of the end, too close to keep
        self.assertEqual(miles(checkpoint_distances_m(100.3 * MILE, 25)), [0, 25, 50, 75, 100.3])

    def test_route_ending_exactly_on_an_interval(self):
        self.assertEqual(miles(checkpoint_distances_m(100 * MILE, 25)), [0, 25, 50, 75, 100])

    def test_short_route_has_only_start_and_end(self):
        self.assertEqual(miles(checkpoint_distances_m(7 * MILE, 25)), [0, 7])

    def test_interval_options(self):
        for interval, expected in ((10, 15), (25, 7), (50, 4)):
            with self.subTest(interval=interval):
                self.assertEqual(len(checkpoint_distances_m(135 * MILE, interval)), expected)

    def test_invalid_inputs(self):
        for total, interval in ((100 * MILE, 0), (100 * MILE, -5), (0, 25)):
            with self.subTest(total=total, interval=interval), self.assertRaises(ValueError):
                checkpoint_distances_m(total, interval)


class SampleCheckpointTests(TestCase):
    def setUp(self):
        self.route = make_route(LOS_ANGELES, DALLAS)  # ~1,236 mi

    def test_not_one_checkpoint_per_geometry_vertex(self):
        self.assertEqual(len(self.route.points), 80)
        self.assertEqual(len(sample_checkpoints(self.route, 50)), 26)

    def test_endpoints_are_exact_and_checkpoints_are_ordered_without_duplicates(self):
        cps = sample_checkpoints(self.route, 25)
        self.assertEqual(cps[0].coordinate, LOS_ANGELES)
        self.assertEqual(cps[-1].coordinate, DALLAS)
        self.assertEqual([cp.index for cp in cps], list(range(len(cps))))
        self.assertEqual(len({cp.coordinate for cp in cps}), len(cps))
        self.assertTrue(all(b.distance_m > a.distance_m for a, b in zip(cps, cps[1:])))

    def test_checkpoints_lie_at_the_stated_distance_along_the_route(self):
        cps = sample_checkpoints(self.route, 25)
        straight_total = haversine_m(LOS_ANGELES, DALLAS)
        for cp in cps[1:-1]:
            self.assertAlmostEqual(
                haversine_m(LOS_ANGELES, cp.coordinate) / straight_total, cp.fraction, delta=0.002
            )

    def test_segments_partition_the_route(self):
        cps = sample_checkpoints(self.route, 25)
        self.assertAlmostEqual(sum(cp.segment_m for cp in cps), self.route.distance_m, places=3)
        self.assertAlmostEqual(cps[0].segment_miles, 12.5)
        self.assertAlmostEqual(cps[1].segment_miles, 25.0)

    def test_provider_distance_differs_from_geometry_length(self):
        route = Route(self.route.points, self.route.distance_m * 1.02, self.route.duration_s)
        cps = sample_checkpoints(route, 50)
        self.assertAlmostEqual(cps[-1].distance_m, route.distance_m)
        self.assertEqual(cps[-1].coordinate, DALLAS)
        mid = cps[len(cps) // 2]
        self.assertAlmostEqual(haversine_m(LOS_ANGELES, mid.coordinate) / haversine_m(LOS_ANGELES, DALLAS), mid.fraction, delta=0.003)

    def test_points_at_distances_requires_ascending(self):
        with self.assertRaises(ValueError):
            points_at_distances(line_points(LOS_ANGELES, DALLAS), [100.0, 50.0])


class ArrivalTimeTests(TestCase):
    def setUp(self):
        self.route = Route(tuple(line_points(LOS_ANGELES, DALLAS)), 200 * MILE, 4 * 3600.0)

    def test_eta_interpolates_linearly_by_distance(self):
        cps = sample_checkpoints(self.route, 50)
        etas = [estimate_arrival(DEPARTURE, self.route, cp) for cp in cps]
        self.assertEqual(etas[0], DEPARTURE)
        self.assertEqual(etas[1], DEPARTURE + timedelta(hours=1))
        self.assertEqual(etas[2], DEPARTURE + timedelta(hours=2))
        self.assertEqual(etas[-1], DEPARTURE + timedelta(hours=4))

    def test_eta_respects_non_uniform_final_leg(self):
        route = Route(self.route.points, 110 * MILE, 11 * 3600.0)
        cps = sample_checkpoints(route, 50)
        self.assertEqual(estimate_arrival(DEPARTURE, route, cps[-1]), DEPARTURE + timedelta(hours=11))
        self.assertAlmostEqual((estimate_arrival(DEPARTURE, route, cps[1]) - DEPARTURE).total_seconds(), 5 * 3600)

    def test_naive_departure_rejected(self):
        cp = sample_checkpoints(self.route, 50)[0]
        with self.assertRaises(ValueError):
            estimate_arrival(datetime(2026, 10, 14, 8, 0), self.route, cp)
