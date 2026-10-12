"""Rank routes and pick the recommendation.

Eligibility: a route is never recommended if it has any No Travel checkpoint, or if weather is known
for less than min_coverage of its miles (it cannot be called safe on little or no data). If no route
is eligible, there is no recommendation (recommended is None); routes are still ordered for display.

Order among eligible routes, in priority:
  0. routes whose weather data is complete before routes with gaps (a gap is not "safe")
  1. fewest Severe miles
  2. fewest High miles
  3. lowest average risk score (mileage-weighted, see aggregation)
  4. shortest travel time
Miles are compared at 0.01 mi resolution and scores at 0.001 so float noise cannot break ties.
Ineligible routes follow, ordered by No Travel miles first, then the same keys (unknown miles are not safe miles).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .aggregation import RouteRiskSummary
from .levels import RiskLevel


@dataclass(frozen=True)
class Ranking:
    order: tuple[int, ...]  # input indexes, best first
    eligible: tuple[bool, ...]  # indexed like the input
    recommended: int | None


DEFAULT_MIN_COVERAGE = 0.8


def rank_routes(
    summaries: Sequence[RouteRiskSummary],
    durations_s: Sequence[float],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Ranking:
    if len(summaries) != len(durations_s):
        raise ValueError("summaries and durations_s must have the same length")
    if not 0 <= min_coverage <= 1:
        raise ValueError("min_coverage must be between 0 and 1")
    eligible = tuple(not s.has_no_travel and s.coverage >= min_coverage for s in summaries)

    def key(i: int):
        s = summaries[i]
        return (
            0 if eligible[i] else 1,
            round(s.miles(RiskLevel.NO_TRAVEL), 2),
            0 if s.data_complete else 1,
            round(s.miles(RiskLevel.SEVERE), 2),
            round(s.miles(RiskLevel.HIGH), 2),
            round(s.average_score, 3) if s.average_score is not None else math.inf,
            durations_s[i],
        )

    order = tuple(sorted(range(len(summaries)), key=key))
    recommended = order[0] if order and eligible[order[0]] else None
    return Ranking(order=order, eligible=eligible, recommended=recommended)
