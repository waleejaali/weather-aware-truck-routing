import math
from collections.abc import Sequence
from dataclasses import dataclass

from .aggregation import RouteRiskSummary
from .levels import RiskLevel


@dataclass(frozen=True)
class Ranking:
    order: tuple[int, ...]  # input indexes, best first
    eligible: tuple[bool, ...]
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
        # Eligibility (no No Travel checkpoint, enough weather coverage) is a gate, not a ranking criterion.
        # Among eligible routes the order is exactly the assignment's: Severe miles, High miles, average risk,
        # travel time. Values are rounded so float noise can't decide a tie. Only when all four tie does complete
        # weather data break the tie (missing data isn't "safe"); after that, input order (fastest first) decides.
        return (
            0 if eligible[i] else 1,
            round(s.miles(RiskLevel.NO_TRAVEL), 2),
            round(s.miles(RiskLevel.SEVERE), 2),
            round(s.miles(RiskLevel.HIGH), 2),
            round(s.average_score, 3) if s.average_score is not None else math.inf,
            durations_s[i],
            0 if s.data_complete else 1,
        )

    order = tuple(sorted(range(len(summaries)), key=key))
    recommended = order[0] if order and eligible[order[0]] else None
    return Ranking(order=order, eligible=eligible, recommended=recommended)
