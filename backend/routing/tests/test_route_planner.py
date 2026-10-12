"""Planner strategy tests using a scripted fake provider (no HTTP at all)."""

from unittest import TestCase

from routing.errors import (
    AlternativeRoutesUnavailable,
    NoRouteFound,
    NoRoutesFoundError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from routing.geometry import haversine_m
from routing.providers.base import RoutingProvider
from routing.services.route_planner import PlannerConfig, RoutePlanner

from .factories import DALLAS, LOS_ANGELES, NEAR_LOS_ANGELES, SAN_DIEGO, make_route, route_from_points, route_via


class FakeProvider(RoutingProvider):
    name = "fake"
    profile = "driving-hgv"
    alternatives_max_distance_m = 100_000.0

    def __init__(self, alternatives=None, directions=None):
        self._alternatives = alternatives
        self._directions = directions
        self.alternative_calls = 0
        self.direction_calls = []  # (waypoints, preference)

    def alternative_routes(self, origin, destination, target_count):
        self.alternative_calls += 1
        if isinstance(self._alternatives, Exception):
            raise self._alternatives
        return list(self._alternatives or [])

    def directions(self, waypoints, *, preference="recommended"):
        self.direction_calls.append((list(waypoints), preference))
        return self._directions(list(waypoints), preference)


def distinct_routes(a, b, count=3):
    """Routes bowed 0, -0.06 and +0.12 degrees: kilometres apart on a short (~25 km) trip."""
    return [make_route(a, b, bulge_deg=bulge) for bulge in (0.0, -0.06, 0.12)[:count]]


def long_trip_directions(waypoints, preference):
    """Plausible provider behaviour for a long trip: shortest == fastest, via points are honoured."""
    origin, destination = waypoints[0], waypoints[-1]
    if len(waypoints) == 3:
        return route_via(origin, waypoints[1], destination)
    if preference == "shortest":
        return make_route(origin, destination, bulge_deg=0.001)  # near-identical to baseline
    return make_route(origin, destination)


class AlternativesPathTests(TestCase):
    def test_three_distinct_provider_alternatives_are_used_directly(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        provider = FakeProvider(alternatives=distinct_routes(a, b))
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual((plan.status, len(plan.routes)), ("complete", 3))
        self.assertEqual(provider.direction_calls, [])
        self.assertEqual({r.strategy for r in plan.routes}, {"provider_alternative"})
        self.assertEqual(plan.profile, "driving-hgv")

    def test_routes_are_sorted_fastest_first_and_share_endpoints(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        plan = RoutePlanner(FakeProvider(alternatives=distinct_routes(a, b)[::-1])).plan(a, b)
        durations = [r.duration_s for r in plan.routes]
        self.assertEqual(durations, sorted(durations))
        for route in plan.routes:
            self.assertEqual(route.points[0], a)
            self.assertEqual(route.points[-1], b)

    def test_duplicate_alternatives_are_removed_and_fallback_tops_up(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        base = make_route(a, b)
        provider = FakeProvider(
            alternatives=[base, make_route(a, b, 0.0005), make_route(a, b, 0.0008)],
            directions=lambda wps, pref: route_via(a, wps[1], b) if len(wps) == 3 else make_route(a, b),
        )
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual(len(plan.routes), 3)
        self.assertTrue(any("overlaps" in n for n in plan.notes))
        self.assertGreaterEqual(sum(r.strategy == "via_waypoint" for r in plan.routes), 2)

    def test_fewer_than_three_returned_is_noted_and_filled(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        provider = FakeProvider(
            alternatives=distinct_routes(a, b, 2),
            directions=lambda wps, pref: route_via(a, wps[1], b),
        )
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual(len(plan.routes), 3)
        self.assertTrue(any("returned 2 alternative" in n for n in plan.notes))

    def test_unreasonable_detour_alternative_is_rejected(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        provider = FakeProvider(
            alternatives=[make_route(a, b), make_route(a, b, 2.0)],  # ~2 deg bulge on a ~25 km trip
            directions=lambda wps, pref: (_ for _ in ()).throw(NoRouteFound("none", status_code=404)),
        )
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual(len(plan.routes), 1)
        self.assertTrue(any("1.5x the baseline" in n for n in plan.notes))

    def test_alternative_with_wrong_endpoint_is_rejected(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        wrong = make_route(a, SAN_DIEGO)
        provider = FakeProvider(
            alternatives=[make_route(a, b), wrong],
            directions=lambda wps, pref: (_ for _ in ()).throw(NoRouteFound("none", status_code=404)),
        )
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual(len(plan.routes), 1)
        self.assertTrue(any("destination" in n for n in plan.notes))

    def test_invalid_geometry_is_rejected(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        broken = route_from_points([a])  # single point
        provider = FakeProvider(alternatives=[broken, make_route(a, b)], directions=lambda w, p: make_route(a, b))
        plan = RoutePlanner(provider, PlannerConfig(max_provider_requests=1)).plan(a, b)
        self.assertEqual(len(plan.routes), 1)
        self.assertTrue(any("fewer than 2 points" in n for n in plan.notes))


class FallbackPathTests(TestCase):
    def test_long_trip_skips_alternatives_and_builds_three_via_waypoint_routes(self):
        provider = FakeProvider(directions=long_trip_directions)
        plan = RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)

        self.assertEqual(provider.alternative_calls, 0)  # certain to exceed the 100 km limit
        self.assertTrue(any("Provider alternatives skipped" in n for n in plan.notes))
        self.assertEqual((plan.status, len(plan.routes)), ("complete", 3))
        self.assertEqual([r.strategy for r in plan.routes].count("baseline"), 1)
        # Duplicate "shortest" candidate was rejected, not returned.
        self.assertTrue(any("shortest_preference" in n and "overlaps" in n for n in plan.notes))

    def test_via_points_are_off_the_straight_line_and_on_both_sides(self):
        provider = FakeProvider(directions=long_trip_directions)
        RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)
        vias = [wps[1] for wps, _ in provider.direction_calls if len(wps) == 3]
        self.assertGreaterEqual(len(vias), 2)
        for wps, _ in provider.direction_calls:
            self.assertEqual((wps[0], wps[-1]), (LOS_ANGELES, DALLAS))
        # Both sides of the corridor are tried: via latitudes straddle the straight-line latitude.
        straight_lat_at = lambda lon: LOS_ANGELES.lat + (DALLAS.lat - LOS_ANGELES.lat) * (
            (lon - LOS_ANGELES.lon) / (DALLAS.lon - LOS_ANGELES.lon)
        )
        offsets = [v.lat - straight_lat_at(v.lon) for v in vias[:2]]
        self.assertLess(offsets[0] * offsets[1], 0)
        for via in vias:
            self.assertGreater(haversine_m(via, LOS_ANGELES), 100_000)

    def test_alternatives_rejected_by_provider_triggers_fallback(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        provider = FakeProvider(
            alternatives=AlternativeRoutesUnavailable("too far", status_code=400, code=2004),
            directions=lambda wps, pref: route_via(a, wps[1], b) if len(wps) == 3 else make_route(a, b),
        )
        plan = RoutePlanner(provider).plan(a, b)
        self.assertEqual(provider.alternative_calls, 1)
        self.assertTrue(any("Provider alternatives failed" in n for n in plan.notes))
        self.assertEqual(plan.status, "complete")

    def test_timeout_on_alternatives_falls_back_instead_of_failing(self):
        a, b = LOS_ANGELES, NEAR_LOS_ANGELES
        provider = FakeProvider(
            alternatives=ProviderTimeoutError("slow"),
            directions=lambda wps, pref: route_via(a, wps[1], b) if len(wps) == 3 else make_route(a, b),
        )
        self.assertEqual(RoutePlanner(provider).plan(a, b).status, "complete")

    def test_partial_result_is_honest_when_via_routes_fail(self):
        def directions(wps, pref):
            if len(wps) == 3:
                raise NoRouteFound("unroutable via point", status_code=404, code=2010)
            return make_route(LOS_ANGELES, DALLAS)

        provider = FakeProvider(directions=directions)
        plan = RoutePlanner(provider, PlannerConfig(max_provider_requests=6)).plan(LOS_ANGELES, DALLAS)
        self.assertEqual((plan.status, len(plan.routes)), ("partial", 1))
        self.assertFalse(plan.is_complete)
        self.assertTrue(any("Only 1 of 3" in n for n in plan.notes))

    def test_request_budget_is_respected(self):
        provider = FakeProvider(directions=lambda wps, pref: (_ for _ in ()).throw(ProviderTimeoutError("slow")) if len(wps) == 3 else make_route(LOS_ANGELES, DALLAS))
        plan = RoutePlanner(provider, PlannerConfig(max_provider_requests=4)).plan(LOS_ANGELES, DALLAS)
        self.assertEqual(len(provider.direction_calls), 4)
        self.assertTrue(any("Stopped after 4" in n for n in plan.notes))
        self.assertEqual(plan.status, "partial")

    def test_rate_limit_stops_fallback_and_returns_what_exists(self):
        def directions(wps, pref):
            if len(wps) == 3:
                raise ProviderRateLimitError("quota")
            return make_route(LOS_ANGELES, DALLAS)

        provider = FakeProvider(directions=directions)
        plan = RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)
        self.assertEqual(len(plan.routes), 1)
        self.assertEqual(len(provider.direction_calls), 3)  # baseline, shortest, one via - then stop
        self.assertTrue(any("rate limit" in n for n in plan.notes))


class FailureTests(TestCase):
    def test_baseline_failure_propagates(self):
        def directions(wps, pref):
            raise ProviderTimeoutError("slow")

        with self.assertRaises(ProviderTimeoutError):
            RoutePlanner(FakeProvider(directions=directions)).plan(LOS_ANGELES, DALLAS)

    def test_auth_error_is_never_swallowed(self):
        with self.assertRaises(ProviderAuthError):
            RoutePlanner(FakeProvider(alternatives=ProviderAuthError("bad key"))).plan(LOS_ANGELES, NEAR_LOS_ANGELES)

    def test_no_valid_route_raises_clear_error(self):
        provider = FakeProvider(directions=lambda wps, pref: route_from_points([LOS_ANGELES]))
        with self.assertRaisesRegex(NoRoutesFoundError, "fewer than 2 points"):
            RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)

    def test_planner_never_changes_profile(self):
        provider = FakeProvider(directions=long_trip_directions)
        plan = RoutePlanner(provider).plan(LOS_ANGELES, DALLAS)
        self.assertEqual(plan.profile, "driving-hgv")
        self.assertEqual(provider.profile, "driving-hgv")
