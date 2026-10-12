"""Per-hazard classification. Inputs are normalized units: wind in mph, rain and snow in inches/hour.

Lower bounds are inclusive. The top "Severe" band is inclusive of its upper edge for rain
(0.50-1.00) and snow (2.0-3.0); No Travel is strictly above it. Wind has no gap: 55 mph is No Travel.
"""

import math

from .levels import RiskLevel

# (exclusive upper bound, level). The first band whose bound is greater than the value wins.
_WIND_MPH = ((25, RiskLevel.LOW), (35, RiskLevel.MODERATE), (45, RiskLevel.HIGH), (55, RiskLevel.SEVERE))
_RAIN_IN_HR = ((0.10, RiskLevel.LOW), (0.25, RiskLevel.MODERATE), (0.50, RiskLevel.HIGH))
_SNOW_IN_HR = ((0.5, RiskLevel.LOW), (1.0, RiskLevel.MODERATE), (2.0, RiskLevel.HIGH))


def classify_wind_mph(wind_mph: float) -> RiskLevel:
    """<25 Low, 25-<35 Moderate, 35-<45 High, 45-<55 Severe, >=55 No Travel."""
    _check(wind_mph, "wind_mph")
    for upper, level in _WIND_MPH:
        if wind_mph < upper:
            return level
    return RiskLevel.NO_TRAVEL


def classify_rain_in_hr(rain_in_hr: float) -> RiskLevel:
    """<0.10 Low, 0.10-<0.25 Moderate, 0.25-<0.50 High, 0.50-1.00 Severe, >1.00 No Travel."""
    _check(rain_in_hr, "rain_in_hr")
    return _classify_with_inclusive_severe(rain_in_hr, _RAIN_IN_HR, severe_max=1.00)


def classify_snow_in_hr(snow_in_hr: float) -> RiskLevel:
    """<0.5 Low, 0.5-<1.0 Moderate, 1.0-<2.0 High, 2.0-3.0 Severe, >3.0 No Travel."""
    _check(snow_in_hr, "snow_in_hr")
    return _classify_with_inclusive_severe(snow_in_hr, _SNOW_IN_HR, severe_max=3.0)


def _classify_with_inclusive_severe(value: float, bands, *, severe_max: float) -> RiskLevel:
    for upper, level in bands:
        if value < upper:
            return level
    return RiskLevel.SEVERE if value <= severe_max else RiskLevel.NO_TRAVEL


def _check(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
