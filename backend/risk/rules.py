from dataclasses import dataclass

from .levels import RiskLevel
from .thresholds import classify_rain_in_hr, classify_snow_in_hr, classify_wind_mph

HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


@dataclass(frozen=True)
class ConditionRisk:
    level: RiskLevel | None
    wind_level: RiskLevel | None
    rain_level: RiskLevel | None
    snow_level: RiskLevel | None
    load_override: RiskLevel | None
    reasons: tuple[str, ...]


def load_override(wind_mph: float, load_lb: float) -> RiskLevel | None:
    # Spec: load must strictly exceed the limit. Wind >= 55 is already No Travel on its own.
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

    # Worst hazard wins, so a load override can only raise the level.
    candidates = [level for level in (wind, rain, snow, override) if level is not None]
    return ConditionRisk(
        level=max(candidates) if candidates else None,
        wind_level=wind,
        rain_level=rain,
        snow_level=snow,
        load_override=override,
        reasons=tuple(reasons),
    )
