import math

from .levels import RiskLevel

# (exclusive upper bound, level) bands from the spec.
_WIND_MPH = ((25, RiskLevel.LOW), (35, RiskLevel.MODERATE), (45, RiskLevel.HIGH), (55, RiskLevel.SEVERE))
_RAIN_IN_HR = ((0.10, RiskLevel.LOW), (0.25, RiskLevel.MODERATE), (0.50, RiskLevel.HIGH))
_SNOW_IN_HR = ((0.5, RiskLevel.LOW), (1.0, RiskLevel.MODERATE), (2.0, RiskLevel.HIGH))


def classify_wind_mph(wind_mph: float) -> RiskLevel:
    _check(wind_mph, "wind_mph")
    for upper, level in _WIND_MPH:
        if wind_mph < upper:
            return level
    return RiskLevel.NO_TRAVEL


def classify_rain_in_hr(rain_in_hr: float) -> RiskLevel:
    _check(rain_in_hr, "rain_in_hr")
    return _classify_with_inclusive_severe(rain_in_hr, _RAIN_IN_HR, severe_max=1.00)


def classify_snow_in_hr(snow_in_hr: float) -> RiskLevel:
    _check(snow_in_hr, "snow_in_hr")
    return _classify_with_inclusive_severe(snow_in_hr, _SNOW_IN_HR, severe_max=3.0)


def _classify_with_inclusive_severe(value: float, bands, *, severe_max: float) -> RiskLevel:
    # The spec's Severe band includes its upper edge for rain (1.00) and snow (3.0); No Travel is strictly above.
    for upper, level in bands:
        if value < upper:
            return level
    return RiskLevel.SEVERE if value <= severe_max else RiskLevel.NO_TRAVEL


def _check(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
