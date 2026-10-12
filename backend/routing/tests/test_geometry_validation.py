from dataclasses import replace
from unittest import TestCase

from routing.geometry import (
    destination_point,
    haversine_m,
    initial_bearing_deg,
    overlap_fraction,
    point_and_bearing_at_fraction,
    resample,
)
from routing.types import Coordinate
from routing.validation import ValidationConfig, integrity_problems, rejection_reason

from .factories import DALLAS, LOS_ANGELES, line_points, make_route

CONFIG = ValidationConfig()


class GeometryTests(TestCase):
    def test_haversine_known_distance(self):
        # Los Angeles - Dallas is roughly 1,990 km great-circle.
        self.assertAlmostEqual(haversine_m(LOS_ANGELES, DALLAS) / 1000, 1990, delta=30)

    def test_destination_point_round_trip(self):
        bearing = initial_bearing_deg(LOS_ANGELES, DALLAS)
        point = destination_point(LOS_ANGELES, bearing, 50_000)
        self.assertAlmostEqual(haversine_m(LOS_ANGELES, point), 50_000, delta=5)

    def test_resample_spacing_and_endpoints(self):
        points = line_points(LOS_ANGELES, DALLAS)
        resampled = resample(points, 10_000)
        self.assertEqual(resampled[0], points[0])
        self.assertEqual(resampled[-1], points[-1])
        self.assertAlmostEqual(haversine_m(resampled[0], resampled[1]), 10_000, delta=200)

    def test_midpoint_and_bearing(self):
        mid, bearing = point_and_bearing_at_fraction(line_points(LOS_ANGELES, DALLAS), 0.5)
        self.assertAlmostEqual(
            haversine_m(LOS_ANGELES, mid) / haversine_m(LOS_ANGELES, DALLAS), 0.5, delta=0.01
        )
        self.assertTrue(60 < bearing < 120)  # roughly east

    def test_overlap_identical_and_disjoint(self):
        a = line_points(LOS_ANGELES, DALLAS)
        far = line_points(LOS_ANGELES, DALLAS, bulge_deg=1.0)
        self.assertEqual(overlap_fraction(a, a), 1.0)
        self.assertLess(overlap_fraction(a, far), 0.2)


class ValidationTests(TestCase):
    def test_valid_route_has_no_problems(self):
        self.assertEqual(integrity_problems(make_route(LOS_ANGELES, DALLAS), LOS_ANGELES, DALLAS, CONFIG), [])

    def test_rejects_short_geometry_and_bad_numbers(self):
        route = make_route(LOS_ANGELES, DALLAS)
        bad = replace(route, points=route.points[:1], distance_m=0.0, duration_s=float("nan"))
        problems = " ".join(integrity_problems(bad, LOS_ANGELES, DALLAS, CONFIG))
        self.assertIn("fewer than 2 points", problems)
        self.assertIn("distance", problems)
        self.assertIn("duration", problems)

    def test_rejects_invalid_coordinates(self):
        route = replace(make_route(LOS_ANGELES, DALLAS), points=(LOS_ANGELES, Coordinate(95.0, 0.0), DALLAS))
        self.assertIn("invalid coordinates", integrity_problems(route, LOS_ANGELES, DALLAS, CONFIG)[0])

    def test_rejects_wrong_endpoints(self):
        route = make_route(LOS_ANGELES, Coordinate(35.0, -97.0))
        problems = integrity_problems(route, LOS_ANGELES, DALLAS, CONFIG)
        self.assertEqual(problems, ["route does not end at the requested destination"])

    def test_detour_rejected(self):
        baseline = make_route(LOS_ANGELES, DALLAS)
        detour = replace(make_route(LOS_ANGELES, DALLAS, 3.0), distance_m=baseline.distance_m * 1.8)
        self.assertIn("distance", rejection_reason(detour, [baseline], baseline, CONFIG))

    def test_slow_route_rejected(self):
        baseline = make_route(LOS_ANGELES, DALLAS)
        slow = replace(make_route(LOS_ANGELES, DALLAS, 1.0), duration_s=baseline.duration_s * 2)
        self.assertIn("duration", rejection_reason(slow, [baseline], baseline, CONFIG))

    def test_duplicate_rejected_and_distinct_accepted(self):
        baseline = make_route(LOS_ANGELES, DALLAS)
        near_copy = make_route(LOS_ANGELES, DALLAS, bulge_deg=0.001)
        distinct = make_route(LOS_ANGELES, DALLAS, bulge_deg=0.8)
        self.assertIn("overlaps", rejection_reason(near_copy, [baseline], baseline, CONFIG))
        self.assertIsNone(rejection_reason(distinct, [baseline], baseline, CONFIG))
