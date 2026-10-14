"""Audit tests: checkpoint placement, ETA arithmetic, geometry validation and route-set edge cases."""

import math
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from routing.checkpoints import METERS_PER_MILE, checkpoint_distances_m, estimate_arrival, sample_checkpoints
from routing.errors import NoRoutesFoundError, ProviderRateLimitError, ProviderRequestError
from routing.geometry import haversine_m, path_length_m, points_at_distances
from routing.services.route_planner import PlannerConfig, RoutePlanner
from routing.types import Coordinate, Route
from routing.validation import ValidationConfig, integrity_problems, rejection_reason

from .factories import DALLAS, LOS_ANGELES, NEAR_LOS_ANGELES, line_points, make_route, route_from_points
from .test_route_planner import FakeProvider, distinct_routes, long_trip_directions

MI = METERS_PER_MILE
UTC = timezone.utc
CFG = ValidationConfig()


def miles(distances):
    return [round(d / MI, 6) for d in distances]


class CheckpointDistanceTests(TestCase):
    def test_route_shorter_than_the_interval_gets_origin_and_destination_only(self):
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                self.assertEqual(miles(checkpoint_distances_m(4 * MI, interval)), [0, 4])

    def test_exact_multiples_have_no_duplicate_final_checkpoint(self):
        self.assertEqual(miles(checkpoint_distances_m(100 * MI, 25)), [0, 25, 50, 75, 100])
        self.assertEqual(miles(checkpoint_distances_m(50 * MI, 50)), [0, 50])
        self.assertEqual(miles(checkpoint_distances_m(30 * MI, 10)), [0, 10, 20, 30])

    def test_remainder_segments_end_at_the_destination(self):
        self.assertEqual(miles(checkpoint_distances_m(110 * MI, 25)), [0, 25, 50, 75, 100, 110])
        self.assertEqual(miles(checkpoint_distances_m(26 * MI, 25)), [0, 25, 26])

    def test_a_regular_checkpoint_within_one_mile_of_the_destination_is_dropped(self):
        self.assertEqual(miles(checkpoint_distances_m(100.5 * MI, 25)), [0, 25, 50, 75, 100.5])
        self.assertEqual(miles(checkpoint_distances_m(101 * MI, 25))[-2:], [75, 101])  # exactly 1 mi away is dropped too
        self.assertEqual(miles(checkpoint_distances_m(101.5 * MI, 25))[-2:], [100, 101.5])  # more than 1 mi is kept

    def test_distances_are_strictly_increasing_and_bounded(self):
        for total_miles in (0.2, 9.99, 10, 10.01, 49.9, 50, 123.456, 2800):
            for interval in (10, 25, 50):
                d = checkpoint_distances_m(total_miles * MI, interval)
                with self.subTest(total=total_miles, interval=interval):
                    self.assertEqual(d[0], 0.0)
                    self.assertAlmostEqual(d[-1], total_miles * MI)
                    self.assertTrue(all(b > a for a, b in zip(d, d[1:])))

    def test_checkpoint_count_for_a_cross_country_trip(self):
        self.assertEqual(len(checkpoint_distances_m(1400 * MI, 10)), 141)
        self.assertEqual(len(checkpoint_distances_m(1400 * MI, 25)), 57)
        self.assertEqual(len(checkpoint_distances_m(1400 * MI, 50)), 29)

    def test_invalid_inputs(self):
        for total, interval in ((0, 25), (-5, 25), (100, 0), (100, -10)):
            with self.subTest(total=total, interval=interval), self.assertRaises(ValueError):
                checkpoint_distances_m(total, interval)


class SampledCheckpointTests(TestCase):
    def setUp(self):
        self.route = make_route(LOS_ANGELES, DALLAS)

    def test_endpoints_are_the_exact_route_endpoints(self):
        cps = sample_checkpoints(self.route, 25)
        self.assertEqual(cps[0].coordinate, self.route.points[0])
        self.assertEqual(cps[-1].coordinate, self.route.points[-1])
        self.assertEqual((cps[0].fraction, cps[-1].fraction), (0.0, 1.0))

    def test_interpolated_points_follow_the_route_and_progress_monotonically(self):
        cps = sample_checkpoints(self.route, 25)
        along = [haversine_m(cps[0].coordinate, cp.coordinate) for cp in cps]
        self.assertTrue(all(b > a for a, b in zip(along, along[1:])))
        for cp in cps:
            nearest = min(haversine_m(cp.coordinate, p) for p in self.route.points)
            self.assertLess(nearest, 25_000)  # within the vertex spacing of this straight test route

    def test_checkpoint_spacing_matches_the_interval(self):
        cps = sample_checkpoints(self.route, 50)
        for a, b in zip(cps[1:-1], cps[2:-1]):
            self.assertAlmostEqual(b.distance_miles - a.distance_miles, 50, places=6)

    def test_segments_tile_the_whole_route_without_gaps_or_overlap(self):
        for interval in (10, 25, 50):
            cps = sample_checkpoints(self.route, interval)
            with self.subTest(interval=interval):
                self.assertAlmostEqual(sum(c.segment_m for c in cps), self.route.distance_m, places=3)
                self.assertTrue(all(c.segment_m > 0 for c in cps))

    def test_indexes_are_sequential(self):
        self.assertEqual([c.index for c in sample_checkpoints(self.route, 25)], list(range(len(sample_checkpoints(self.route, 25)))))

    def test_short_route_has_two_checkpoints(self):
        short = route_from_points(line_points(LOS_ANGELES, Coordinate(34.0522, -118.2000), n=5))
        cps = sample_checkpoints(short, 25)
        self.assertEqual(len(cps), 2)
        self.assertAlmostEqual(sum(c.segment_m for c in cps), short.distance_m)

    def test_repeated_vertices_do_not_break_interpolation(self):
        pts = line_points(LOS_ANGELES, NEAR_LOS_ANGELES, n=10)
        pts = pts[:3] + [pts[2], pts[2]] + pts[3:] + [pts[-1]]
        route = route_from_points(pts)
        cps = sample_checkpoints(route, 10)
        for cp in cps:
            self.assertTrue(math.isfinite(cp.coordinate.lat) and math.isfinite(cp.coordinate.lon))

    def test_provider_distance_differing_from_geometry_length_is_rescaled_not_overrun(self):
        pts = line_points(LOS_ANGELES, DALLAS)
        route = Route(tuple(pts), path_length_m(pts) * 1.2, 36_000.0)  # provider says 20% longer
        cps = sample_checkpoints(route, 50)
        self.assertEqual(cps[-1].coordinate, pts[-1])
        mid = cps[len(cps) // 2]
        along = haversine_m(pts[0], mid.coordinate) / haversine_m(pts[0], pts[-1])
        self.assertAlmostEqual(along, mid.fraction, delta=0.01)

    def test_points_at_distances_requires_ascending_input_and_clamps(self):
        pts = line_points(LOS_ANGELES, NEAR_LOS_ANGELES, n=5)
        with self.assertRaises(ValueError):
            points_at_distances(pts, [10.0, 5.0])
        out = points_at_distances(pts, [-5.0, 1e12])
        self.assertEqual((out[0], out[1]), (pts[0], pts[-1]))


class EtaTests(TestCase):
    def setUp(self):
        pts = line_points(LOS_ANGELES, DALLAS)
        self.route = Route(tuple(pts), 1400 * MI, 20 * 3600.0)
        self.cps = sample_checkpoints(self.route, 50)

    def test_eta_is_linear_in_checkpoint_fraction_and_ends_at_arrival(self):
        dep = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
        etas = [estimate_arrival(dep, self.route, c) for c in self.cps]
        self.assertEqual(etas[0], dep)
        self.assertEqual(etas[-1], dep + timedelta(hours=20))
        self.assertTrue(all(b > a for a, b in zip(etas, etas[1:])))
        for c, eta in zip(self.cps, etas):
            self.assertAlmostEqual((eta - dep).total_seconds(), 72_000 * c.fraction, places=3)

    def test_naive_departure_is_rejected(self):
        with self.assertRaises(ValueError):
            estimate_arrival(datetime(2026, 10, 14, 8, 0), self.route, self.cps[0])

    def test_equal_instants_in_different_offsets_give_equal_utc_etas(self):
        a = datetime(2026, 10, 14, 8, 0, tzinfo=timezone(timedelta(hours=-5)))
        b = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
        for c in self.cps:
            self.assertEqual(estimate_arrival(a, self.route, c), estimate_arrival(b, self.route, c))

    def test_arrival_across_a_dst_fall_back_is_measured_in_elapsed_time_not_wall_clock(self):
        # 2026-11-01 01:30 EDT (UTC-4) leaves 20 h of driving, spanning the 02:00 EDT -> 01:00 EST change.
        dep = datetime(2026, 11, 1, 1, 30, tzinfo=timezone(timedelta(hours=-4)))
        end = estimate_arrival(dep, self.route, self.cps[-1])
        self.assertEqual(end.astimezone(UTC), datetime(2026, 11, 1, 5, 30, tzinfo=UTC) + timedelta(hours=20))

    def test_arrival_across_a_dst_spring_forward(self):
        dep = datetime(2026, 3, 8, 1, 30, tzinfo=timezone(timedelta(hours=-5)))  # 06:30Z, before the 07:00Z change
        end = estimate_arrival(dep, self.route, self.cps[-1])
        self.assertEqual(end - dep, timedelta(hours=20))

    def test_a_day_boundary_in_utc_is_crossed_correctly(self):
        dep = datetime(2026, 10, 14, 23, 0, tzinfo=UTC)
        mid = next(c for c in self.cps if c.fraction > 0.4)
        eta = estimate_arrival(dep, self.route, mid)
        self.assertEqual(eta.date(), datetime(2026, 10, 15).date())


class IntegrityValidationTests(TestCase):
    A, B = LOS_ANGELES, NEAR_LOS_ANGELES

    def route(self, points=None, distance=40_000.0, duration=2400.0):
        return Route(tuple(points if points is not None else line_points(self.A, self.B)), distance, duration)

    def problems(self, route):
        return integrity_problems(route, self.A, self.B, CFG)

    def test_a_good_route_has_no_problems(self):
        self.assertEqual(self.problems(self.route()), [])

    def test_geometry_too_short(self):
        self.assertTrue(self.problems(self.route(points=[])))
        self.assertTrue(self.problems(self.route(points=[self.A])))

    def test_invalid_coordinates(self):
        base = line_points(self.A, self.B)
        for bad in (Coordinate(91, 0), Coordinate(-91, 0), Coordinate(0, 181), Coordinate(0, -181),
                    Coordinate(float("nan"), 0), Coordinate(0, float("inf"))):
            with self.subTest(bad=bad):
                self.assertIn("geometry contains invalid coordinates", self.problems(self.route(points=base + [bad])))

    def test_lat_lon_swapped_geometry_is_caught(self):
        swapped = [Coordinate(p.lon, p.lat) for p in line_points(self.A, self.B)]  # lat becomes -118
        self.assertTrue(self.problems(self.route(points=swapped)))
        # A swap that stays in range is caught by the endpoint check instead.
        europe_a, europe_b = Coordinate(48.85, 2.35), Coordinate(50.85, 4.35)
        swapped_eu = [Coordinate(p.lon, p.lat) for p in line_points(europe_a, europe_b)]
        found = integrity_problems(Route(tuple(swapped_eu), 40_000, 2400), europe_a, europe_b, CFG)
        self.assertTrue(any("start at the requested origin" in p for p in found))

    def test_endpoint_tolerance_edges(self):
        pts = line_points(self.A, self.B)
        near = Coordinate(self.A.lat + 1_000 / 111_000, self.A.lon)  # ~1 km: inside the 1.5 km tolerance
        far = Coordinate(self.A.lat + 2_000 / 111_000, self.A.lon)  # ~2 km: outside
        self.assertEqual(self.problems(self.route(points=[near] + pts[1:])), [])
        self.assertTrue(any("origin" in p for p in self.problems(self.route(points=[far] + pts[1:]))))
        self.assertTrue(any("destination" in p for p in self.problems(self.route(points=pts[:-1] + [far]))))

    def test_bad_distance_and_duration(self):
        for bad in (0, -1, float("nan"), float("inf"), -float("inf")):
            with self.subTest(bad=bad):
                self.assertTrue(any("distance" in p for p in self.problems(self.route(distance=bad))))
                self.assertTrue(any("duration" in p for p in self.problems(self.route(duration=bad))))

    def test_all_problems_are_reported_together(self):
        found = self.problems(self.route(distance=0, duration=-1))
        self.assertEqual(len(found), 2)


class RejectionTests(TestCase):
    def test_identical_geometry_is_a_duplicate(self):
        a = make_route(LOS_ANGELES, NEAR_LOS_ANGELES)
        self.assertIn("overlaps", rejection_reason(a, [a], a, CFG))

    def test_nearly_identical_geometry_is_a_duplicate(self):
        a = make_route(LOS_ANGELES, NEAR_LOS_ANGELES)
        b = make_route(LOS_ANGELES, NEAR_LOS_ANGELES, bulge_deg=0.0005)  # ~50 m off
        self.assertIn("overlaps", rejection_reason(b, [a], a, CFG))

    def test_a_route_fully_inside_a_longer_one_is_a_duplicate(self):
        long = make_route(LOS_ANGELES, NEAR_LOS_ANGELES)
        part = route_from_points(long.points[:40])
        self.assertIn("overlaps", rejection_reason(part, [long], long, ValidationConfig(max_detour_ratio=10)))

    def test_a_distinct_route_is_accepted(self):
        a = make_route(LOS_ANGELES, NEAR_LOS_ANGELES)
        b = make_route(LOS_ANGELES, NEAR_LOS_ANGELES, bulge_deg=0.1)
        self.assertIsNone(rejection_reason(b, [a], a, CFG))

    def test_absurd_detours_are_rejected_by_distance_and_by_duration(self):
        base = Route(tuple(line_points(LOS_ANGELES, NEAR_LOS_ANGELES)), 100_000, 4000)
        long_distance = Route(base.points, 151_000, 4000)
        long_duration = Route(base.points, 100_000, 6_001)
        self.assertIn("distance", rejection_reason(long_distance, [], base, CFG))
        self.assertIn("duration", rejection_reason(long_duration, [], base, CFG))
        self.assertIsNone(rejection_reason(Route(base.points, 150_000, 6_000), [], base, CFG))


class PlannerTruthfulnessTests(TestCase):
    A, B = LOS_ANGELES, NEAR_LOS_ANGELES

    def test_three_copies_of_one_geometry_become_one_route_and_a_partial_plan(self):
        r = make_route(self.A, self.B)
        provider = FakeProvider(alternatives=[r, r, r], directions=lambda w, p: r)
        plan = RoutePlanner(provider, PlannerConfig(max_provider_requests=3)).plan(self.A, self.B)
        self.assertEqual(len(plan.routes), 1)
        self.assertEqual(plan.status, "partial")
        self.assertTrue(any("Only 1 of 3" in n for n in plan.notes))

    def test_two_distinct_alternatives_plus_failed_fallbacks_yield_two_routes_and_a_note(self):
        routes = distinct_routes(self.A, self.B, 2)

        def directions(waypoints, preference):
            if len(waypoints) == 2 and preference == "recommended":
                return routes[0]
            raise ProviderRequestError("nope", status_code=400)

        plan = RoutePlanner(FakeProvider(alternatives=routes, directions=directions)).plan(self.A, self.B)
        self.assertEqual((len(plan.routes), plan.status), (2, "partial"))
        self.assertEqual(plan.requested_count, 3)

    def test_routes_are_returned_fastest_first(self):
        routes = distinct_routes(self.A, self.B)
        plan = RoutePlanner(FakeProvider(alternatives=list(reversed(routes)))).plan(self.A, self.B)
        durations = [r.duration_s for r in plan.routes]
        self.assertEqual(durations, sorted(durations))

    def test_no_valid_route_is_an_error_not_an_empty_plan(self):
        bad = Route(tuple(line_points(self.A, self.B)), 0.0, 0.0)
        provider = FakeProvider(alternatives=[bad], directions=lambda w, p: bad)
        with self.assertRaises(NoRoutesFoundError):
            RoutePlanner(provider).plan(self.A, self.B)

    def test_provider_returning_nothing_is_an_error(self):
        provider = FakeProvider(alternatives=[], directions=lambda w, p: (_ for _ in ()).throw(ProviderRequestError("x")))
        with self.assertRaises(ProviderRequestError):
            RoutePlanner(provider).plan(self.A, self.B)

    def test_long_trips_skip_alternatives_and_still_build_three_routes_with_a_request_cap(self):
        provider = FakeProvider(alternatives=[], directions=long_trip_directions)
        plan = RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)
        self.assertEqual(provider.alternative_calls, 0)
        self.assertEqual((plan.status, len(plan.routes)), ("complete", 3))
        self.assertLessEqual(len(provider.direction_calls), PlannerConfig().max_provider_requests)
        self.assertTrue(any("alternatives skipped" in n for n in plan.notes))

    def test_rate_limit_during_fallbacks_returns_what_was_found(self):
        calls = {"n": 0}

        def directions(waypoints, preference):
            calls["n"] += 1
            if calls["n"] >= 3:
                raise ProviderRateLimitError("slow down")
            return long_trip_directions(waypoints, preference)

        plan = RoutePlanner(FakeProvider(alternatives=[], directions=directions)).plan(LOS_ANGELES, DALLAS)
        self.assertEqual(plan.status, "partial")
        self.assertTrue(any("rate limit" in n for n in plan.notes))
        self.assertGreaterEqual(len(plan.routes), 1)
