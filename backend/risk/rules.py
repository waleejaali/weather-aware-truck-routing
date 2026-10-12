"""Combine hazard levels with the load rules into one checkpoint risk.

Precedence: the result is the HIGHEST of (wind level, rain level, snow level, load override).
Load overrides can only raise the level, never lower it. Load comparisons are strict (">").

Load rules (wind in mph, load in lb):
    wind >= 55                    -> No Travel, any load (already the wind band itself)
    45 <= wind < 55 and load > 30,000 -> No Travel
    35 <= wind < 45 and load > 40,000 -> Severe
"""

from dataclasses import dataclass

from .levels import RiskLevel
from .thresholds import classify_rain_in_hr, classify_snow_in_hr, classify_wind_mph

HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


@dataclass(frozen=True)
class ConditionRisk:
    level: RiskLevel | None  # None only when no hazard value was available
    wind_level: RiskLevel | None
    rain_level: RiskLevel | None
    snow_level: RiskLevel | None
    load_override: RiskLevel | None  # level forced by a load rule, if one applied
    reasons: tuple[str, ...]


def load_override(wind_mph: float, load_lb: float) -> RiskLevel | None:
    if 45 <= wind_mph < 55 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return RiskLevel.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lb > HEAVY_LOAD_SEVERE_LB:
        return RiskLevel.SEVERE
    return None


def assess_conditions(
    *,
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_lb: float,
) -> ConditionRisk:
    """Risk for one checkpoint. A hazard whose value is None (unavailable) is skipped, not assumed zero."""
    if load_lb < 0:
        raise ValueError("load_lb must be non-negative")
    reasons: list[str] = []
    wind = rain = snow = override = None

    if wind_mph is not None:
        wind = classify_wind_mph(wind_mph)
        reasons.append(f"wind {wind_mph:g} mph: {wind.label}")
        override = load_override(wind_mph, load_lb)
        if override is not None:
            reasons.append(f"load {load_lb:,.0f} lb with wind {wind_mph:g} mph: {override.label}")
    if rain_in_hr is not None:
        rain = classify_rain_in_hr(rain_in_hr)
        reasons.append(f"rain {rain_in_hr:g} in/hr: {rain.label}")
    if snow_in_hr is not None:
        snow = classify_snow_in_hr(snow_in_hr)
        reasons.append(f"snow {snow_in_hr:g} in/hr: {snow.label}")

    candidates = [level for level in (wind, rain, snow, override) if level is not None]
    return ConditionRisk(
        level=max(candidates) if candidates else None,
        wind_level=wind,
        rain_level=rain,
        snow_level=snow,
        load_override=override,
        reasons=tuple(reasons),
    )
