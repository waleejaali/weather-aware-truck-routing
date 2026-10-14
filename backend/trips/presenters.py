"""Domain objects -> the JSON response of POST /api/v1/routes/assess/. Pure: no I/O, no Django.

Everything here is read from the pipeline's results. Missing weather stays null (never 0), and the
risk levels, eligibility and ranking are exactly what the risk engine decided.
"""

from datetime import datetime, timezone
from typing import Any

from risk.levels import RiskLevel
from routing.checkpoints import METERS_PER_MILE
from trips.assessment import (
    STATUS_INSUFFICIENT_WEATHER,
    STATUS_NO_SAFE_ROUTE,
    STATUS_RECOMMENDED,
    STATUS_RECOMMENDED_INCOMPLETE,
    CheckpointAssessment,
    RouteAssessment,
    TripAssessment,
)
from trips.batch import BatchResult, DepartureOutcome
from trips.services import TripResult

API_VERSION = "v1"
UNITS = {
    "distance": "mi",
    "duration": "s",
    "wind_speed": "mph",
    "rain_rate": "in/hr",
    "snow_rate": "in/hr",
    "load": "lb",
    "timestamps": "ISO 8601, UTC (Z)",
    "geometry_coordinates": "GeoJSON order: [longitude, latitude] (Leaflet's L.geoJSON handles this; "
    "L.polyline expects [latitude, longitude])",
}
_LEVEL_KEYS = {
    RiskLevel.LOW: "low",
    RiskLevel.MODERATE: "moderate",
    RiskLevel.HIGH: "high",
    RiskLevel.SEVERE: "severe",
    RiskLevel.NO_TRAVEL: "no_travel",
}
RISK_LEGEND = [{"key": _LEVEL_KEYS[level], "label": level.label, "score": int(level)} for level in RiskLevel]


def present_result(result: TripResult, params: dict[str, Any]) -> dict[str, Any]:
    trip, plan = result.assessment, result.plan
    ordered = trip.routes
    recommended = trip.recommended
    return {
        "api_version": API_VERSION,
        "request": {
            "origin": params["origin"],
            "destination": params["destination"],
            "departure_datetime": _iso(params["departure"]),
            "departure_datetime_input": params["departure_input"],
            "load_lb": params["load_lb"],
            "checkpoint_interval_miles": params["interval_miles"],
        },
        "units": UNITS,
        "risk_levels": RISK_LEGEND,
        "recommendation": {
            "status": trip.status,
            "recommended_route_id": _route_id(recommended) if recommended else None,
            "explanation": _recommendation_text(trip),
        },
        "method": {
            "wind_metric": trip.wind_metric,
            "checkpoint_interval_miles": trip.interval_miles,
            "min_weather_coverage_percent": round(trip.min_weather_coverage * 100),
            "assumptions": list(trip.assumptions),
            "routing": {
                "provider": plan.provider,
                "profile": plan.profile,
                "status": plan.status,
                "requested_routes": plan.requested_count,
                "returned_routes": len(plan.routes),
                "notes": list(plan.notes),
            },
            "weather": {
                "provider": result.weather_provider_name,
                "attribution": {
                    "text": trip.attribution.text,
                    "url": trip.attribution.url,
                    "license": trip.attribution.license,
                    "license_url": trip.attribution.license_url,
                },
            },
            "notes": list(trip.notes),
        },
        "routes": [_route(r, ordered) for r in ordered],
    }


def _route(r: RouteAssessment, ordered: tuple[RouteAssessment, ...], *, include_geometry: bool = True) -> dict[str, Any]:
    s = r.summary
    data = {
        "id": _route_id(r),
        "source": r.route.strategy,
        "rank": r.rank,
        "recommended": r.recommended,
        "eligible": r.eligible,
        "ineligible_reason": r.ineligible_reason,
        "distance_miles": round(r.route.distance_m / METERS_PER_MILE, 1),
        "duration_seconds": round(r.route.duration_s),
        "duration_text": _duration_text(r.route.duration_s),
        "departure_datetime": _iso(r.departure),
        "arrival_datetime": _iso(r.arrival),
        "geometry": _geometry(r),
        "risk_summary": {
            "miles": {
                **{_LEVEL_KEYS[level]: round(s.miles(level), 2) for level in RiskLevel},
                "unknown": round(s.unknown_miles, 2),
            },
            "average_score": None if s.average_score is None else round(s.average_score, 3),
            "weather_coverage_percent": round(s.coverage * 100, 1),
            "weather_data_complete": s.data_complete,
            "max_risk_level": None if s.max_level is None else _LEVEL_KEYS[s.max_level],
            "no_travel_checkpoints": s.no_travel_checkpoints,
        },
        "ranking": {
            "keys": {
                "no_travel_miles": round(s.miles(RiskLevel.NO_TRAVEL), 2),
                "weather_data_complete": s.data_complete,
                "severe_miles": round(s.miles(RiskLevel.SEVERE), 2),
                "high_miles": round(s.miles(RiskLevel.HIGH), 2),
                "average_score": None if s.average_score is None else round(s.average_score, 3),
                "duration_seconds": round(r.route.duration_s),
            },
            "explanation": _ranking_explanation(r, ordered),
        },
        "checkpoints": [_checkpoint(c) for c in r.checkpoints],
    }
    if not include_geometry:
        del data["geometry"]
    return data


def _geometry(r: RouteAssessment) -> dict[str, Any]:
    return {
        "type": "LineString",
        "coordinates": [[round(p.lon, 5), round(p.lat, 5)] for p in r.route.points],
    }


def _checkpoint(c: CheckpointAssessment) -> dict[str, Any]:
    cond, risk = c.conditions, c.risk
    return {
        "index": c.checkpoint.index,
        "distance_miles": round(c.checkpoint.distance_miles, 1),
        "segment_miles": round(c.checkpoint.segment_miles, 2),
        "latitude": round(c.checkpoint.coordinate.lat, 5),
        "longitude": round(c.checkpoint.coordinate.lon, 5),
        "eta": _iso(c.eta),
        "weather_status": "unavailable" if cond is None else ("complete" if c.complete else "partial"),
        "weather_missing_reason": c.unavailable_reason,
        "weather": {
            "wind_speed_mph": _r(cond and cond.wind_mph),
            "wind_gust_mph": _r(cond and cond.gust_mph),
            "rain_in_per_hr": _r(cond and cond.rain_in_hr),
            "snow_in_per_hr": _r(cond and cond.snow_in_hr),
            "wind_used_mph": _r(c.wind_mph_used),
        },
        "risk": {
            "combined": _key(risk and risk.level),
            "wind": _key(risk and risk.wind_level),
            "rain": _key(risk and risk.rain_level),
            "snow": _key(risk and risk.snow_level),
            "load_override": _key(risk and risk.load_override),
            "reasons": list(risk.reasons) if risk else [],
        },
    }


# -- explanations --------------------------------------------------------------------------------


def _recommendation_text(trip: TripAssessment) -> str:
    caveat = " This is based on forecast conditions at sampled checkpoints and is not a guarantee of safety."
    r = trip.recommended
    if trip.status == STATUS_NO_SAFE_ROUTE:
        return "No route is recommended: every route has at least one No Travel checkpoint for this load and departure time."
    if trip.status == STATUS_INSUFFICIENT_WEATHER:
        return (
            "No route is recommended: weather data is too incomplete to compare these routes. "
            "Missing weather does not mean conditions are safe."
        )
    assert r is not None
    why = _ranking_explanation(r, trip.routes)
    if trip.status == STATUS_RECOMMENDED_INCOMPLETE:
        return (
            f"{_route_id(r)} is recommended ({why.rstrip('.')}), but weather data is missing for part of it, "
            f"so its risk may be understated.{caveat}"
        )
    assert trip.status == STATUS_RECOMMENDED
    return f"{_route_id(r)} is recommended. {why}{caveat}"


def _ranking_explanation(r: RouteAssessment, ordered: tuple[RouteAssessment, ...]) -> str:
    if not r.eligible:
        return f"Not eligible for recommendation: {r.ineligible_reason}."
    position = r.rank - 1  # `ordered` is sorted by rank
    if position == 0:
        nxt = next((o for o in ordered[1:] if o.eligible), None)
        if nxt is None:
            return "Ranked first: the only route eligible for recommendation."
        return f"Ranked first over {_route_id(nxt)}: {_decisive(r, nxt)}."
    better = ordered[position - 1]
    return f"Ranked below {_route_id(better)}, which has {_decisive(better, r)}."


def _decisive(better: RouteAssessment, worse: RouteAssessment) -> str:
    """The first ranking criterion (in the risk engine's order) on which `better` beats `worse`."""
    a, b = better.summary, worse.summary
    if a.data_complete and not b.data_complete:
        return "complete weather data where the other route has gaps"
    for level, name in ((RiskLevel.SEVERE, "Severe"), (RiskLevel.HIGH, "High")):
        x, y = round(a.miles(level), 2), round(b.miles(level), 2)
        if x < y:
            return f"fewer {name} miles ({x:g} vs {y:g})"
    if a.average_score is not None and b.average_score is not None:
        x, y = round(a.average_score, 3), round(b.average_score, 3)
        if x < y:
            return f"a lower average risk score ({x:g} vs {y:g})"
    if better.route.duration_s < worse.route.duration_s:
        return (
            f"a shorter travel time ({_duration_text(better.route.duration_s)} vs "
            f"{_duration_text(worse.route.duration_s)})"
        )
    return "equal ranking on every criterion"


# -- small helpers ---------------------------------------------------------------------------------


def _route_id(r: RouteAssessment) -> str:
    return f"route-{r.plan_index + 1}"


def _key(level: RiskLevel | None) -> str | None:
    return None if level is None else _LEVEL_KEYS[level]


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_text(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


# -- batch response ---------------------------------------------------------------------------------


def present_batch(result: BatchResult, params: dict[str, Any]) -> dict[str, Any]:
    """Response for POST /api/v1/routes/assess-batch/.

    Route geometry is identical for every departure, so it is sent once in `routes` and each result's
    routes refer to it by id. Everything else per route is exactly what the single endpoint returns.
    """
    plan = result.plan
    first = next((o.assessment for o in result.outcomes if o.assessment is not None), None)
    assert first is not None  # the view rejects batches where nothing could be assessed
    return {
        "api_version": API_VERSION,
        "generated_at": _iso(result.generated_at),
        "request": {
            "origin": params["origin"],
            "destination": params["destination"],
            "load_lb": params["load_lb"],
            "checkpoint_interval_miles": params["interval_miles"],
            "departure_datetimes": [_iso(o.departure) for o in result.outcomes],
        },
        "units": UNITS,
        "risk_levels": RISK_LEGEND,
        "method": {
            "wind_metric": first.wind_metric,
            "checkpoint_interval_miles": first.interval_miles,
            "min_weather_coverage_percent": round(first.min_weather_coverage * 100),
            "assumptions": list(first.assumptions),
            "routing": {
                "provider": plan.provider,
                "profile": plan.profile,
                "status": plan.status,
                "requested_routes": plan.requested_count,
                "returned_routes": len(plan.routes),
                "notes": list(plan.notes),
            },
            "weather": {
                "provider": result.weather_provider_name,
                "attribution": {
                    "text": first.attribution.text,
                    "url": first.attribution.url,
                    "license": first.attribution.license,
                    "license_url": first.attribution.license_url,
                },
            },
        },
        "diagnostics": {
            "route_cache": "hit" if result.route_cache_hit else "miss",
            "routing_provider_requests": result.routing_requests,
            "weather_provider_requests": result.weather_requests,
        },
        "routes": [_shared_route(i, route) for i, route in enumerate(plan.routes)],
        "results": [_outcome(i, o) for i, o in enumerate(result.outcomes)],
    }


def _shared_route(index: int, route) -> dict[str, Any]:
    return {
        "id": f"route-{index + 1}",
        "source": route.strategy,
        "distance_miles": round(route.distance_m / METERS_PER_MILE, 1),
        "duration_seconds": round(route.duration_s),
        "geometry": {
            "type": "LineString",
            "coordinates": [[round(p.lon, 5), round(p.lat, 5)] for p in route.points],
        },
    }


def _outcome(index: int, outcome: DepartureOutcome) -> dict[str, Any]:
    base = {
        "index": index,
        "departure_datetime": _iso(outcome.departure),
        "departure_datetime_input": outcome.departure_input,
    }
    trip = outcome.assessment
    if trip is None:
        return {**base, "ok": False, "error": {"code": outcome.error_code, "message": outcome.error_message}}
    return {
        **base,
        "ok": True,
        "recommendation": {
            "status": trip.status,
            "recommended_route_id": _route_id(trip.recommended) if trip.recommended else None,
            "explanation": _recommendation_text(trip),
        },
        "notes": list(trip.notes),
        "routes": [_route(r, trip.routes, include_geometry=False) for r in trip.routes],
    }
