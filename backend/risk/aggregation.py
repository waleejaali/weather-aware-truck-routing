"""Aggregate checkpoint risks into a per-route summary.

Each checkpoint represents the stretch of road closest to it along the route (its "segment": half
way to each neighbouring checkpoint), so a checkpoint's level is APPLIED to segment_miles of road.
"Miles at level X" is therefore an estimate built from sampled points, not a measurement of every
mile: a hazard that falls between two checkpoints can be missed. Scoring: Low=0, Moderate=1, High=2,
Severe=3, No Travel=4. average_score is the mileage-weighted mean score over miles whose risk
is known; unknown miles are reported separately and never counted as Low.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .levels import RiskLevel


@dataclass(frozen=True)
class CheckpointRisk:
    level: RiskLevel | None  # None: weather unavailable for this checkpoint
    segment_miles: float
    complete: bool  # False if any weather value needed for the level was missing


@dataclass(frozen=True)
class RouteRiskSummary:
    miles_by_level: dict[RiskLevel, float]
    known_miles: float
    unknown_miles: float
    average_score: float | None  # None if no miles have a known level
    max_level: RiskLevel | None
    no_travel_checkpoints: int
    data_complete: bool  # every checkpoint had every needed weather value

    @property
    def has_no_travel(self) -> bool:
        return self.no_travel_checkpoints > 0

    @property
    def total_miles(self) -> float:
        return self.known_miles + self.unknown_miles

    @property
    def coverage(self) -> float:
        """Share (0-1) of the route's miles whose risk could be determined."""
        return self.known_miles / self.total_miles if self.total_miles > 0 else 0.0

    def miles(self, level: RiskLevel) -> float:
        return self.miles_by_level[level]


def summarize(checkpoints: Sequence[CheckpointRisk]) -> RouteRiskSummary:
    miles = {level: 0.0 for level in RiskLevel}
    unknown = 0.0
    for cp in checkpoints:
        if cp.level is None:
            unknown += cp.segment_miles
        else:
            miles[cp.level] += cp.segment_miles
    known = sum(miles.values())
    levels = [cp.level for cp in checkpoints if cp.level is not None]
    return RouteRiskSummary(
        miles_by_level=miles,
        known_miles=known,
        unknown_miles=unknown,
        average_score=(sum(level * m for level, m in miles.items()) / known) if known > 0 else None,
        max_level=max(levels) if levels else None,
        no_travel_checkpoints=sum(1 for level in levels if level == RiskLevel.NO_TRAVEL),
        data_complete=all(cp.complete for cp in checkpoints),
    )
