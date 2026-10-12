"""Route planning strategy: provider alternatives first, waypoint-constrained fallback second.

Provider-agnostic: talks only to the RoutingProvider interface and the pure validation module.
Every candidate, whatever its source, goes through the same integrity, detour and
duplicate checks. The result is honest: "complete" only if the requested number of distinct,
valid routes was found, otherwise "partial" (with notes explaining why), or an error if none.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace

from ..errors import (
    NoRoutesFoundError,
    ProviderAuthError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    RoutingProviderError,
)
from ..geometry import destination_point, haversine_m, point_and_bearing_at_fraction
from ..providers.base import RoutingProvider
from ..types import Coordinate, Route
from ..validation import ValidationConfig, integrity_problems, rejection_reason

# Failures that make further requests pointless; they propagate instead of triggering fallbacks.
_FATAL_ERRORS = (ProviderConfigurationError, ProviderAuthError)

STRATEGY_ALTERNATIVE = "provider_alternative"
STRATEGY_BASELINE = "baseline"
STRATEGY_SHORTEST = "shortest_preference"
STRATEGY_VIA = "via_waypoint"


@dataclass(frozen=True)
class PlannerConfig:
    target_route_count: int = 3
    # Upper bound on provider calls per plan (protects the free-tier quota).
    max_provider_requests: int = 10
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    # Fallback via-point placement: fractions along the baseline, and sideways offsets
    # = clamp(offset_ratio * baseline_distance, min, max) * multiplier, tried on both sides.
    via_fractions: tuple[float, ...] = (0.5, 0.3, 0.7)
    via_offset_multipliers: tuple[float, ...] = (1.0, 0.5, 1.5)
    via_offset_ratio: float = 0.12
    via_offset_min_m: float = 5_000.0
    via_offset_max_m: float = 100_000.0


@dataclass(frozen=True)
class RoutePlan:
    routes: tuple[Route, ...]  # fastest first
    status: str  # "complete" (target count reached) or "partial"
    provider: str
    profile: str
    requested_count: int
    notes: tuple[str, ...]  # human-readable account of what was tried, skipped or rejected

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"


class _PlanState:
    def __init__(self, origin: Coordinate, destination: Coordinate):
        self.origin = origin
        self.destination = destination
        self.accepted: list[Route] = []
        self.baseline: Route | None = None
        self.notes: list[str] = []
        self.requests_used = 0


class RoutePlanner:
    def __init__(self, provider: RoutingProvider, config: PlannerConfig | None = None):
        self._provider = provider
        self._config = config or PlannerConfig()

    def plan(self, origin: Coordinate, destination: Coordinate) -> RoutePlan:
        state = _PlanState(origin, destination)
        self._try_provider_alternatives(state)
        if len(state.accepted) < self._config.target_route_count:
            self._fill_with_waypoint_routes(state)
        if not state.accepted:
            raise NoRoutesFoundError("No valid route could be produced. " + " | ".join(state.notes))

        complete = len(state.accepted) >= self._config.target_route_count
        if not complete:
            state.notes.append(
                f"Only {len(state.accepted)} of {self._config.target_route_count} distinct routes could be found."
            )
        return RoutePlan(
            routes=tuple(sorted(state.accepted, key=lambda r: r.duration_s))[: self._config.target_route_count],
            status="complete" if complete else "partial",
            provider=self._provider.name,
            profile=self._provider.profile,
            requested_count=self._config.target_route_count,
            notes=tuple(state.notes),
        )

    # -- strategy 1: provider alternatives ------------------------------------------------------

    def _try_provider_alternatives(self, state: _PlanState) -> None:
        limit = self._provider.alternatives_max_distance_m
        straight_line = haversine_m(state.origin, state.destination)
        if limit is not None and straight_line > limit:
            # The route can never be shorter than the straight line, so the request would be refused.
            state.notes.append(
                f"Provider alternatives skipped: trip is at least {straight_line / 1000:.0f} km, "
                f"over the provider's {limit / 1000:.0f} km limit for alternative routes."
            )
            return
        try:
            routes = self._call(
                state, lambda: self._provider.alternative_routes(
                    state.origin, state.destination, self._config.target_route_count
                )
            )
        except _FATAL_ERRORS:
            raise
        except RoutingProviderError as exc:
            state.notes.append(f"Provider alternatives failed: {exc}")
            return
        if len(routes) < self._config.target_route_count:
            state.notes.append(f"Provider returned {len(routes)} alternative route(s), expected {self._config.target_route_count}.")
        self._accept_batch(state, routes, STRATEGY_ALTERNATIVE)

    # -- strategy 2: waypoint-constrained fallback -----------------------------------------------

    def _fill_with_waypoint_routes(self, state: _PlanState) -> None:
        if state.baseline is None:
            # No baseline from alternatives: this request must succeed, so errors propagate.
            route = self._call(state, lambda: self._provider.directions([state.origin, state.destination]))
            self._accept_batch(state, [route], STRATEGY_BASELINE)
            if state.baseline is None:
                return  # baseline failed validation; notes explain why

        for strategy, request in self._fallback_candidates(state):
            if len(state.accepted) >= self._config.target_route_count:
                return
            if state.requests_used >= self._config.max_provider_requests:
                state.notes.append(f"Stopped after {self._config.max_provider_requests} provider requests.")
                return
            try:
                route = self._call(state, request)
            except _FATAL_ERRORS:
                raise
            except ProviderRateLimitError as exc:
                state.notes.append(f"Stopped early, provider rate limit reached: {exc}")
                return
            except RoutingProviderError as exc:
                state.notes.append(f"{strategy} candidate failed: {exc}")
                continue
            self._accept_batch(state, [route], strategy)

    def _fallback_candidates(self, state: _PlanState) -> Iterator[tuple[str, Callable[[], Route]]]:
        origin, destination = state.origin, state.destination
        yield STRATEGY_SHORTEST, lambda: self._provider.directions([origin, destination], preference="shortest")

        baseline = state.baseline
        assert baseline is not None
        offset_base = min(
            max(self._config.via_offset_ratio * baseline.distance_m, self._config.via_offset_min_m),
            self._config.via_offset_max_m,
        )
        for multiplier in self._config.via_offset_multipliers:
            for fraction in self._config.via_fractions:
                anchor, bearing = point_and_bearing_at_fraction(baseline.points, fraction)
                for side in (90.0, -90.0):
                    via = destination_point(anchor, (bearing + side) % 360, offset_base * multiplier)
                    yield STRATEGY_VIA, lambda via=via: self._provider.directions([origin, via, destination])

    # -- shared ---------------------------------------------------------------------------------

    def _call(self, state: _PlanState, request: Callable):
        state.requests_used += 1
        return request()

    def _accept_batch(self, state: _PlanState, routes: list[Route], strategy: str) -> None:
        valid = []
        for route in routes:
            problems = integrity_problems(route, state.origin, state.destination, self._config.validation)
            if problems:
                state.notes.append(f"Rejected {strategy} route: {'; '.join(problems)}.")
            else:
                valid.append(replace(route, strategy=strategy))
        valid.sort(key=lambda r: r.duration_s)

        if state.baseline is None and valid:
            # Fastest valid route anchors the detour check; later candidates are measured against it.
            state.baseline = valid[0]
        for route in valid:
            reason = rejection_reason(route, state.accepted, state.baseline, self._config.validation)
            if reason is None:
                state.accepted.append(route)
            else:
                state.notes.append(f"Rejected {strategy} route: {reason}.")
