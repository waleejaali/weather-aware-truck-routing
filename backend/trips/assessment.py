from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from risk.aggregation import CheckpointRisk, RouteRiskSummary, summarize
from risk.levels import RiskLevel
from risk.ranking import DEFAULT_MIN_COVERAGE, rank_routes
from risk.rules import ConditionRisk, assess_conditions
from routing.checkpoints import Checkpoint, estimate_arrival, sample_checkpoints
from routing.types import Route
from weather.providers.base import WeatherProvider
from weather.sampling import SampledConditions, ceil_hour, floor_hour, sample_conditions
from weather.types import Attribution

ALLOWED_INTERVALS_MILES = (10, 25, 50)
WIND_METRICS = ("sustained", "gust")

STATUS_RECOMMENDED = "recommended"
STATUS_RECOMMENDED_INCOMPLETE = "recommended_incomplete_weather"
STATUS_NO_SAFE_ROUTE = "no_safe_route"
STATUS_INSUFFICIENT_WEATHER = "insufficient_weather_data"


@dataclass(frozen=True)
class CheckpointAssessment:
    checkpoint: Checkpoint
    eta: datetime  # UTC
    conditions: SampledConditions | None
    risk: ConditionRisk | None
    complete: bool
    unavailable_reason: str | None
    wind_mph_used: float | None = None

    @property
    def level(self) -> RiskLevel | None:
        return None if self.risk is None else self.risk.level


@dataclass(frozen=True)
class RouteAssessment:
    route: Route
    plan_index: int
    departure: datetime
    arrival: datetime
    checkpoints: tuple[CheckpointAssessment, ...]
    summary: RouteRiskSummary
    rank: int  # 1 = best
    eligible: bool
    ineligible_reason: str | None
    recommended: bool

    @property
    def weather_coverage(self) -> float:
        return self.summary.coverage

    @property
    def no_travel_checkpoints(self) -> tuple[CheckpointAssessment, ...]:
        return tuple(c for c in self.checkpoints if c.level == RiskLevel.NO_TRAVEL)


@dataclass(frozen=True)
class TripAssessment:
    routes: tuple[RouteAssessment, ...]  # best first
    recommended: RouteAssessment | None
    status: str
    notes: tuple[str, ...]
    attribution: Attribution
    interval_miles: float
    load_lb: float
    wind_metric: str
    min_weather_coverage: float
    assumptions: tuple[str, ...]


def assess_routes(
    routes: Sequence[Route],
    *,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    provider: WeatherProvider,
    now: datetime,
    wind_metric: str = "sustained",
    min_weather_coverage: float = DEFAULT_MIN_COVERAGE,
) -> TripAssessment:
    if not routes:
        raise ValueError("routes must not be empty")
    if departure.tzinfo is None or now.tzinfo is None:
        raise ValueError("departure and now must be timezone-aware")
    if interval_miles not in ALLOWED_INTERVALS_MILES:
        raise ValueError(f"interval_miles must be one of {ALLOWED_INTERVALS_MILES}")
    if wind_metric not in WIND_METRICS:
        raise ValueError(f"wind_metric must be one of {WIND_METRICS}")
    if load_lb < 0:
        raise ValueError("load_lb must be non-negative")
    if not 0 <= min_weather_coverage <= 1:
        raise ValueError("min_weather_coverage must be between 0 and 1")
    departure = departure.astimezone(timezone.utc)

    window_start, window_end = provider.available_window(now)
    notes: list[str] = []

    sampled = []
    for route in routes:
        checkpoints = sample_checkpoints(route, interval_miles)
        sampled.append([(cp, estimate_arrival(departure, route, cp)) for cp in checkpoints])

    # Checkpoints outside the provider's window stay unavailable; we never substitute weather from another time.
    requests_: list[tuple[int, int]] = []  # (route_index, checkpoint_index)
    unavailable: dict[tuple[int, int], str] = {}
    for r, items in enumerate(sampled):
        for c, (cp, eta) in enumerate(items):
            if floor_hour(eta) < window_start or ceil_hour(eta) >= window_end:
                kind = "beyond the forecast horizon" if ceil_hour(eta) >= window_end else "before the available history"
                unavailable[(r, c)] = (
                    f"arrival {eta:%Y-%m-%d %H:%M} UTC is {kind} "
                    f"({window_start:%Y-%m-%d} to {window_end:%Y-%m-%d} UTC)"
                )
            else:
                requests_.append((r, c))
    if unavailable:
        notes.append(
            f"{len(unavailable)} checkpoint(s) have no weather because their arrival time is outside "
            "the provider's available range; no other weather was substituted."
        )

    series_by_request: dict[tuple[int, int], object] = {}
    if requests_:
        etas = [sampled[r][c][1] for r, c in requests_]
        series = provider.fetch_hourly(
            [sampled[r][c][0].coordinate for r, c in requests_], floor_hour(min(etas)), ceil_hour(max(etas))
        )
        series_by_request = dict(zip(requests_, series))

    assessed: list[list[CheckpointAssessment]] = []
    for r, items in enumerate(sampled):
        row = []
        for c, (cp, eta) in enumerate(items):
            conditions = risk = wind_used = None
            reason = unavailable.get((r, c))
            if (r, c) in series_by_request:
                conditions = sample_conditions(series_by_request[(r, c)], eta)
                wind_used = conditions.wind_mph if wind_metric == "sustained" else conditions.gust_mph
                risk = assess_conditions(
                    wind_mph=wind_used,
                    rain_in_hr=conditions.rain_in_hr,
                    snow_in_hr=conditions.snow_in_hr,
                    load_lb=load_lb,
                )
                needed = {"wind" if wind_metric == "sustained" else "gust", "rain", "snow"}
                gaps = sorted(needed & set(conditions.missing))
                if gaps:
                    reason = f"provider has no {', '.join(gaps)} data for the hour of arrival"
            row.append(
                CheckpointAssessment(cp, eta.astimezone(timezone.utc), conditions, risk, reason is None, reason, wind_used)
            )
        assessed.append(row)

    summaries = [
        summarize([CheckpointRisk(a.level, a.checkpoint.segment_miles, a.complete) for a in row]) for row in assessed
    ]
    ranking = rank_routes(summaries, [route.duration_s for route in routes], min_weather_coverage)
    rank_of = {index: position + 1 for position, index in enumerate(ranking.order)}

    results = {
        i: RouteAssessment(
            route=routes[i],
            plan_index=i,
            departure=departure,
            arrival=departure + timedelta(seconds=routes[i].duration_s),
            checkpoints=tuple(assessed[i]),
            summary=summaries[i],
            rank=rank_of[i],
            eligible=ranking.eligible[i],
            ineligible_reason=_ineligible_reason(summaries[i], min_weather_coverage),
            recommended=(i == ranking.recommended),
        )
        for i in range(len(routes))
    }
    ordered = tuple(results[i] for i in ranking.order)
    recommended = results[ranking.recommended] if ranking.recommended is not None else None

    for r in ordered:
        if r.ineligible_reason:
            notes.append(f"Route {r.plan_index + 1} cannot be recommended: {r.ineligible_reason}.")
    if recommended is None:
        if all(r.summary.has_no_travel for r in ordered):
            status = STATUS_NO_SAFE_ROUTE
            notes.append("Every route has at least one No Travel checkpoint; no route is recommended.")
        else:
            status = STATUS_INSUFFICIENT_WEATHER
            notes.append(
                "Weather data is too incomplete to compare these routes, so no route is recommended "
                "(and none should be treated as safe)."
            )
    elif not recommended.summary.data_complete:
        status = STATUS_RECOMMENDED_INCOMPLETE
        notes.append("The recommended route has checkpoints with missing weather data; its risk may be understated.")
    else:
        status = STATUS_RECOMMENDED
    if recommended and recommended.summary.data_complete and any(
        r.eligible and not r.summary.data_complete for r in ordered
    ):
        notes.append("Routes with missing weather data are ranked after routes with complete data.")

    return TripAssessment(
        routes=ordered,
        recommended=recommended,
        status=status,
        notes=tuple(notes),
        attribution=provider.attribution,
        interval_miles=interval_miles,
        load_lb=load_lb,
        wind_metric=wind_metric,
        min_weather_coverage=min_weather_coverage,
        assumptions=_assumptions(interval_miles, wind_metric, min_weather_coverage),
    )


def _ineligible_reason(summary: RouteRiskSummary, min_coverage: float) -> str | None:
    if summary.has_no_travel:
        return f"{summary.no_travel_checkpoints} checkpoint(s) are No Travel"
    if summary.coverage < min_coverage:
        return f"weather is known for only {summary.coverage:.0%} of its miles (minimum {min_coverage:.0%})"
    return None


def _assumptions(interval_miles: float, wind_metric: str, min_coverage: float) -> tuple[str, ...]:
    wind = (
        "sustained 10 m wind speed (wind_speed_10m); gusts are not used"
        if wind_metric == "sustained"
        else "10 m wind gusts (wind_gusts_10m, max of the preceding hour); sustained speed is not used"
    )
    return (
        "This is a recommendation based on forecast conditions at sampled checkpoints, "
        "not a guarantee that any route is safe.",
        f"Weather is sampled at checkpoints about every {interval_miles:g} miles, not along every mile; "
        "hazards between checkpoints can be missed.",
        "Miles at each risk level are estimates: each checkpoint's level is applied to the road halfway "
        "to its neighbouring checkpoints.",
        f"Wind risk uses {wind}.",
        "Arrival times assume constant average speed over the whole route.",
        f"A route needs weather for at least {min_coverage:.0%} of its miles to be recommended.",
    )
