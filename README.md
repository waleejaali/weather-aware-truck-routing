# Weather-Aware Truck Routing

Compare three driving routes for a truck based on weather along the route, load weight, estimated checkpoint arrival times, and travel duration.

> **Status:** backend routing, weather, risk and recommendation logic with a REST API (`POST /api/v1/routes/assess/`), tests and live-check commands, and a React dashboard with map, checkpoint table and forecast slider.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, Leaflet + React Leaflet, axios |
| Backend | Python, Django 6, Django REST Framework, django-cors-headers |
| External APIs (planned) | OpenRouteService (routing/geocoding), Open-Meteo (weather) |

## Structure

```
backend/
  config/      Django settings and root URLs
  core/        Health endpoint
  routing/     Route generation (providers/ = API adapters, services/ = planning strategy,
               geometry.py + validation.py = pure logic, management/commands/ = live check)
  weather/     Weather retrieval (providers/ = Open-Meteo adapter)
  risk/        Pure risk thresholds, load rules, aggregation and ranking (no Django/network imports)
  trips/       Orchestration (assessment.py, services.py) and the REST endpoint (serializers.py, views.py, presenters.py)
frontend/      React + TypeScript + Vite app
.env.example   Environment variable template
```

## Prerequisites

- Python 3.12+ (developed on 3.15)
- Node.js 20.19+ (developed on 24) and npm

## Setup (Windows PowerShell)

Run from the repository root.

```powershell
# 1. Environment variables
Copy-Item .env.example .env
# Edit .env: set DJANGO_SECRET_KEY and ORS_API_KEY

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..

# 3. Frontend
cd frontend
npm install
cd ..
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Run

Two terminals, started independently.

```powershell
# Terminal 1 - backend on http://localhost:8000
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

```powershell
# Terminal 2 - frontend on http://localhost:5173
cd frontend
npm run dev
```

Open http://localhost:5173. The page shows "Backend reachable" when the API is up. You can also check http://localhost:8000/api/health/.

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | backend | Required unless `DJANGO_DEBUG=true` |
| `DJANGO_DEBUG` | backend | `true` for local development |
| `DJANGO_ALLOWED_HOSTS` | backend | Comma-separated hostnames |
| `FRONTEND_URL` | backend | Comma-separated origins allowed by CORS |
| `ORS_API_KEY` | backend | OpenRouteService key. Backend only; never sent to the browser |
| `ORS_BASE_URL` | backend | ORS API base URL |
| `ORS_PROFILE` | backend | Vehicle profile, default `driving-hgv` (truck). Never changed automatically |
| `ORS_TIMEOUT_SECONDS` | backend | Per-request timeout, default 30 |
| `OPEN_METEO_BASE_URL` | backend | Open-Meteo API base URL (no key needed for the free tier) |
| `WEATHER_TIMEOUT_SECONDS` | backend | Per-request timeout, default 20 |
| `WEATHER_WIND_METRIC` | backend | `sustained` (default, `wind_speed_10m`) or `gust` (`wind_gusts_10m`) drives wind risk |
| `VITE_API_BASE_URL` | frontend | Backend base URL |

`.env` is git-ignored; only `.env.example` is committed.

## Checks

```powershell
# Backend tests
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py test

# Frontend type-check + production build, and lint
cd frontend
npm run build
npm run lint
```

## Routing strategy

`routing.services.route_planner.RoutePlanner` returns up to three distinct routes for an origin/destination
(`RoutePlan`: routes fastest-first, `status`, `profile`, `notes`). It only talks to the `RoutingProvider`
interface (`routing/providers/base.py`), so the provider or strategy can change without touching callers.

1. **Provider alternatives first.** ORS `alternative_routes` (`target_count=3`) is tried only when the straight-line
   distance is within ORS's documented 100 km limit for alternatives. Longer trips skip it, since a route is never shorter
   than the straight line. If ORS still refuses (HTTP 400, code 2004), times out or errors, the planner records a note and falls back.
2. **Waypoint-constrained fallback.** One baseline route (`recommended`), then a `shortest`-preference route, then
   routes forced through a *via point* placed sideways of the baseline (at 50%, 30% and 70% of its length, on both sides,
   offset 12% of the trip length, clamped to 5-100 km, then smaller/larger offsets). Via points get a wide road-snapping
   radius (20 km); end points 1 km. Total provider calls are capped (`max_provider_requests`, default 10) to protect the free quota.
3. **Validation on every candidate, whatever its source** (`routing/validation.py`): geometry has at least two valid points,
   positive finite distance and duration, route starts/ends within 1.5 km of the requested points, no more than 1.5x the
   baseline's distance or duration, and shares less than 90% of its length (within 500 m) with an already accepted route.
4. **Honest results.** `status="complete"` only with 3 valid distinct routes. Otherwise `status="partial"` with the
   routes found and notes saying why, or `NoRoutesFoundError` if there are none. Routes are never invented or repeated.
5. **Truck profile is explicit.** The profile comes from `ORS_PROFILE` (default `driving-hgv`), is reported on every plan,
   and is never switched to car routing on failure. Auth, quota and missing-key errors are surfaced, not masked.

### Known limitations

- ORS hosted-API limits come from <https://openrouteservice.org/restrictions/>: alternatives <= 100 km and <= 3 routes,
  avoid-areas <= 150 km (so avoid polygons cannot diversify long trips), 50 waypoints; free tier 2,000 directions requests/day, 40/min.
  The page does not list a `driving-hgv` distance limit, so long HGV trips are **unverified until the live check below**.
- Whether via-point routes are distinct enough on real roads depends on the road network; the thresholds above are starting
  values that need tuning against live results. Expect `partial` on some corridors with a single dominant highway.
- Truck load is not sent to ORS (no weight restrictions on routing); load only affects weather risk later.
- ORS error code 2004 for the alternatives limit is based on ORS documentation and forum reports and is confirmed only by the live check.
- Only US-style mid-latitude geometry is assumed by the overlap grid.

### Live check (real API, uses your key)

Put your key in the repo-root `.env` (`ORS_API_KEY=...`, never commit it), then:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py check_routing                       # Los Angeles -> Dallas
python manage.py check_routing --origin 34.0522,-118.2437 --destination 32.7767,-96.7970 --max-requests 12

# Short trip (Dallas -> Fort Worth, under 100 km): exercises ORS alternative_routes directly
python manage.py check_routing --origin 32.7767,-96.7970 --destination 32.7555,-97.3308

# Tune the heuristics while inspecting results
python manage.py check_routing --max-detour-ratio 1.8 --max-overlap 0.95
```

Overlap is distance-based: both routes are resampled every 500 m along their length, and the score is the share of the
shorter route that lies within 500 m of the other, so differing vertex densities do not matter.

It prints provider, profile, status, each route's distance (mi), duration, strategy and overlap with the others, plus the
notes explaining what was skipped or rejected. A missing key gives an error explaining how to set it. This command is
separate from the automated tests, which use mocked HTTP and need no key.

## Weather and risk

`trips.assessment.assess_routes(routes, departure=, load_lb=, interval_miles=, provider=, now=)` assesses planned routes and
returns them ranked, with a recommendation (or none). Layers: `routing/checkpoints.py` (sampling, ETA), `weather/` (provider +
hour selection), `risk/` (pure rules, aggregation, ranking).

### Checkpoints and arrival times
- Checkpoints every 10, 25 or 50 miles of route distance from the origin, plus the destination. A checkpoint within 1 mile
  (or half an interval, if smaller) of the destination is dropped so the end is not duplicated. Raw geometry vertices are never used.
- ETA assumes constant average speed: `departure + duration * (distance along route / route distance)`. The routing provider
  returns one duration per route, so traffic, hills and urban slowdowns are not modelled.
- Each checkpoint stands for the road halfway to its neighbours (its "segment"); miles by risk level are summed over segments.

### Weather data (Open-Meteo, server-side only)
- One batched request per 50 unique locations (all routes together; locations are de-duplicated at ~1 km), in mph and inches,
  with UTC epoch timestamps. Every response's units are checked and rejected if unexpected.
- **Snowfall** is snow depth (not water equivalent) summed over the *preceding hour*, converted from cm to inches by the API when
  `precipitation_unit=inch` (verified against the live API). A one-hour sum is numerically inches per hour, so it is used directly as in/hr.
  **Rain** is `rain + showers` (liquid). `precipitation` is not used because it includes snow.
- Which hourly record applies at arrival time t: sustained wind is linearly interpolated between the hours either side of t;
  gusts, rain and snow use the record stamped at the next whole hour, whose "preceding hour" window contains t.
- **Availability:** the free API serves about 92 days back to 16 days ahead (`available_window`). Checkpoints whose arrival falls outside it are
  reported as unavailable with a reason, not requested, and never filled with current or other-hour weather. Missing hours or null fields
  are reported the same way. A weather API failure raises a typed error (timeout, rate limit, bad response).
- **Attribution (required):** data is CC BY 4.0, "Weather data by Open-Meteo.com" with a link to https://open-meteo.com/. The footer of the
  React app shows it and `TripAssessment.attribution` carries it for the future API payload; any results page must display it.
  **Permitted use:** per Open-Meteo's [terms](https://open-meteo.com/en/terms) the free API is for non-commercial use only (examples: private or
  non-profit apps without subscriptions or ads, educational content) and limited to under 10,000 calls/day, 5,000/hour and 600/minute.
  Commercial use needs a paid plan, and a company assignment demo may or may not qualify; confirm with Open-Meteo or switch providers
  before public hosting. The provider sits behind `weather.providers.base.WeatherProvider`, so replacing it touches only
  `weather/providers/` (a long trip is roughly 100-250 locations per assessment).

### Risk rules
| Hazard | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | <25 | 25-<35 | 35-<45 | 45-<55 | >=55 |
| Rain (in/hr) | <0.10 | 0.10-<0.25 | 0.25-<0.50 | 0.50-1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5-<1.0 | 1.0-<2.0 | 2.0-3.0 | >3.0 |

Load rules (strict `>`): wind 45-<55 mph with load > 30,000 lb is No Travel; wind 35-<45 mph with load > 40,000 lb is Severe.
**Precedence:** a checkpoint's risk is the highest of its wind, rain and snow levels and any load override; overrides only raise it.

### Aggregation and recommendation
- A checkpoint's risk is *applied* to its segment, the road halfway to each neighbouring checkpoint. "Miles at risk level X" is
  therefore an estimate from sampled points, not a measurement of every mile; hazards between checkpoints can be missed. The checkpoint
  spacing is configurable (10/25/50) and reported in the result (`interval_miles`, plus `assumptions` strings meant to be shown with results).
- Score: Low 0, Moderate 1, High 2, Severe 3, No Travel 4. Average risk is the mileage-weighted mean over miles with known risk;
  unknown miles are reported separately (`unknown_miles`, `weather_coverage`), never counted as Low.
- **Eligibility:** a route is never recommended if it has any No Travel checkpoint, or if weather is known for less than 80% of its
  miles (`min_weather_coverage`, configurable). Missing weather is not safety.
- **Order among eligible routes:** complete-weather routes before routes with gaps, then fewest Severe miles, fewest High miles,
  lowest average score, shortest time.
- **Status** (`TripAssessment.status`): `recommended`; `recommended_incomplete_weather` (the winner has some gaps, risk may be understated);
  `no_safe_route` (every route has a No Travel checkpoint); `insufficient_weather_data` (no route has enough weather to compare or
  recommend; nothing should be treated as safe). In the last two, `recommended` is `None`.
- **Wording:** results are a recommendation from forecast conditions at sampled checkpoints, not a guarantee of safety. Any UI must show the
  weather coverage, sampling interval, wind metric and the estimated-miles method next to the recommendation (all are in the result; see `assumptions`).
- **Wind metric:** exactly one of sustained wind or gusts feeds the rules, never a mix. It is in `TripAssessment.wind_metric`, in the
  `assumptions` text, and per checkpoint as `wind_mph_used`. Sustained is the default because the assignment says "wind" without defining it.

### Assumptions to review
- The 80% weather-coverage minimum and the wind-metric default are judgement calls, not assignment requirements.
- Rain intensity is the hourly liquid total, not a peak rate within the hour.

### Run
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py test                      # offline: mocked HTTP, no keys
python manage.py check_weather --departure 2026-10-14T08:00:00-05:00 --load-lb 42000 --checkpoints   # live ORS + Open-Meteo
```

## REST API

Base URL in development: `http://localhost:8000`. JSON in, JSON out. No authentication. CORS allows the origins in `FRONTEND_URL`.

### `POST /api/v1/routes/assess/`

Plans up to three truck routes (OpenRouteService, `driving-hgv`), samples weather at each checkpoint's estimated arrival time
(Open-Meteo), classifies risk with the load rules, ranks the routes and says whether any can be recommended. It runs the same
pipeline as `python manage.py check_weather` (`trips/services.py`). It makes live provider calls, so it needs `ORS_API_KEY` and
takes a few seconds for long trips. Responses are gzip-compressed when the client sends `Accept-Encoding: gzip`.

**Request**

```json
{
  "origin": {"latitude": 34.0522, "longitude": -118.2437},
  "destination": {"latitude": 32.7767, "longitude": -96.7970},
  "departure_datetime": "2026-10-14T08:00:00-05:00",
  "load_lb": 42000,
  "checkpoint_interval_miles": 25
}
```

| Field | Rules |
| --- | --- |
| `origin`, `destination` | objects with numeric `latitude` (-90..90) and `longitude` (-180..180); at least 100 m apart |
| `departure_datetime` | ISO 8601 **with a UTC offset** (`-05:00` or `Z`). Times without an offset are rejected, never assumed to be UTC. Converted to UTC internally |
| `load_lb` | number, greater than 0 and at most 150,000 |
| `checkpoint_interval_miles` | exactly 10, 25 or 50 |

Numbers must be JSON numbers (strings, booleans, NaN and infinity are rejected). Unknown fields are ignored.
Geocoding is not part of this API: send coordinates.

```bash
curl -s -X POST http://localhost:8000/api/v1/routes/assess/ \
  -H "Content-Type: application/json" \
  -d '{"origin":{"latitude":34.0522,"longitude":-118.2437},"destination":{"latitude":32.7767,"longitude":-96.7970},"departure_datetime":"2026-10-14T08:00:00-05:00","load_lb":42000,"checkpoint_interval_miles":25}'
```

Choose a departure within the weather forecast window (about 92 days back to 16 days ahead); checkpoints outside it are
reported as unavailable.

**Response (200)** - abridged

```json
{
  "api_version": "v1",
  "request": {"origin": {...}, "destination": {...}, "departure_datetime": "2026-10-14T13:00:00Z",
              "departure_datetime_input": "2026-10-14T08:00:00-05:00", "load_lb": 42000.0, "checkpoint_interval_miles": 25},
  "units": {"distance": "mi", "duration": "s", "wind_speed": "mph", "rain_rate": "in/hr", "snow_rate": "in/hr", "...": "..."},
  "risk_levels": [{"key": "low", "label": "Low", "score": 0}, "... moderate, high, severe, no_travel"],
  "recommendation": {
    "status": "recommended",
    "recommended_route_id": "route-1",
    "explanation": "route-1 is recommended. Ranked first over route-2: fewer High miles (0 vs 25). This is based on forecast conditions at sampled checkpoints and is not a guarantee of safety."
  },
  "method": {
    "wind_metric": "sustained", "checkpoint_interval_miles": 25, "min_weather_coverage_percent": 80,
    "assumptions": ["..."],
    "routing": {"provider": "openrouteservice", "profile": "driving-hgv", "status": "complete",
                "requested_routes": 3, "returned_routes": 3, "notes": ["Provider alternatives skipped: ..."]},
    "weather": {"provider": "open-meteo", "attribution": {"text": "Weather data by Open-Meteo.com", "url": "https://open-meteo.com/", "license": "CC BY 4.0", "license_url": "..."}},
    "notes": ["..."]
  },
  "routes": [
    {
      "id": "route-1", "source": "baseline", "rank": 1, "recommended": true,
      "eligible": true, "ineligible_reason": null,
      "distance_miles": 1430.1, "duration_seconds": 119340, "duration_text": "33 h 9 min",
      "departure_datetime": "2026-10-14T13:00:00Z", "arrival_datetime": "2026-10-15T22:09:00Z",
      "geometry": {"type": "LineString", "coordinates": [[-118.2437, 34.0522], "... [longitude, latitude]"]},
      "risk_summary": {
        "miles": {"low": 1430.1, "moderate": 0.0, "high": 0.0, "severe": 0.0, "no_travel": 0.0, "unknown": 0.0},
        "average_score": 0.0, "weather_coverage_percent": 100.0, "weather_data_complete": true,
        "max_risk_level": "low", "no_travel_checkpoints": 0
      },
      "ranking": {"keys": {"no_travel_miles": 0.0, "weather_data_complete": true, "severe_miles": 0.0, "high_miles": 0.0,
                           "average_score": 0.0, "duration_seconds": 119340},
                  "explanation": "Ranked first over route-2: ..."},
      "checkpoints": [
        {"index": 1, "distance_miles": 25.0, "segment_miles": 25.0, "latitude": 34.07, "longitude": -117.8,
         "eta": "2026-10-14T13:45:00Z",
         "weather_status": "complete", "weather_missing_reason": null,
         "weather": {"wind_speed_mph": 8.2, "wind_gust_mph": 11.6, "rain_in_per_hr": 0.0, "snow_in_per_hr": 0.0, "wind_used_mph": 8.2},
         "risk": {"combined": "low", "wind": "low", "rain": "low", "snow": "low", "load_override": null, "reasons": ["wind 8.2 mph: Low", "..."]}}
      ]
    }
  ]
}
```

Notes on the contract:
- `routes` is ordered by `rank` (1 = best) and always contains every candidate. `route-N` ids are stable within a response only.
- **`recommendation.status`**: `recommended`; `recommended_incomplete_weather` (winner has some missing weather, risk may be understated);
  `no_safe_route` (every route has a No Travel checkpoint); `insufficient_weather_data` (no route has enough weather data to compare).
  In the last two, `recommended_route_id` is `null`. These are results (HTTP 200), not errors. Missing weather never means safe.
- **Geometry** is a GeoJSON `LineString` with `[longitude, latitude]` pairs rounded to 5 decimals. Use `L.geoJSON(...)` in Leaflet,
  or swap each pair for `L.polyline`.
- **Weather values are `null` when unavailable**, never 0. `weather_status` is `complete`, `partial` (some fields missing; known hazards are
  still classified) or `unavailable`, with `weather_missing_reason`.
- `risk_summary.miles` are estimates: each checkpoint's risk is applied to the road halfway to its neighbours (see "Aggregation and recommendation").
- Timestamps are ISO 8601 UTC ending in `Z`. Durations are seconds, distances miles, wind mph, rain and snow inches/hour.
- `method.assumptions` and `method.routing.notes` (for example why provider alternatives were skipped) should be shown with the results.
- Display `method.weather.attribution` wherever weather data is shown.

**Errors** use one shape and never include stack traces, keys or provider payloads (details go to the server log):

```json
{"error": {"code": "validation_error", "message": "The request is invalid.",
           "fields": {"departure_datetime": ["Include a UTC offset (for example -05:00 or Z); times without one are ambiguous."]}}}
```

| Status | `error.code` | When |
| --- | --- | --- |
| 400 | `validation_error` (with `fields`, keyed like `origin.latitude`, `body`), `invalid_json` | invalid input or malformed JSON |
| 405 / 415 | `method_not_allowed` / `unsupported_media_type` | not POST / not `application/json` |
| 422 | `no_route_found` | inputs are valid but no drivable route exists |
| 502 | `routing_failed`, `weather_failed` | the provider returned an error or unusable data |
| 503 | `routing_unavailable`, `routing_rate_limited`, `weather_rate_limited` | missing/rejected credentials, or quota/rate limit |
| 504 | `routing_timeout`, `weather_timeout` | the provider did not answer in time |
| 500 | `internal_error` | unexpected failure |

A routing failure is never returned as a successful empty list. A weather *provider* failure fails the request (502/504); weather that
is merely unavailable for some checkpoints (outside the forecast range, missing hours) is reported per checkpoint with the reasons above.

`GET /api/health/` is unchanged and does not call any external service.

Tests for this contract are in `backend/trips/tests/test_api.py` (fake providers; no network or keys).

## Frontend (React dashboard)

A single-page dashboard in `frontend/` (React 19, TypeScript, Vite, Tailwind CSS v4, Leaflet via React Leaflet, axios) that calls
`POST /api/v1/routes/assess/` and shows the routes, risk, checkpoints and map.

### Configure and run

| Variable | Where | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | repo-root `.env` (read by Vite via `envDir: '..'`) | Backend base URL, no trailing path. Defaults to `http://localhost:8000` |
| `ROUTE_CACHE_TTL_SECONDS` | repo-root `.env` (backend) | How long planned routes are reused between batch requests (default 900; 0 disables) |
| `FRONTEND_URL` | repo-root `.env` (backend) | The frontend origin(s) the backend's CORS allows; must include where the app is served from, e.g. `http://localhost:5173` |

`VITE_*` values are baked into the bundle at build time and are visible to anyone using the app, so they must never hold secrets.
The ORS key stays in the backend; the browser only talks to your Django API. For a deployment, build with `VITE_API_BASE_URL` set to
the deployed API's URL and add the deployed frontend's origin to the backend's `FRONTEND_URL`.

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173 (start the backend too: python manage.py runserver)
npm run build        # type-check + production build into frontend/dist
npm run lint
npm test             # Vitest + Testing Library (no network, no API keys)
```

### What the dashboard does
- **Form:** origin and destination as latitude/longitude (the API accepts coordinates, not addresses, and no geocoder is configured), departure
  date-time in the browser's time zone (sent with its UTC offset), load in pounds, and 10/25/50-mile checkpoint spacing, with inline validation
  that mirrors the backend rules. Three quick-fill trips are provided.
- **Results:** every candidate route with rank, recommended badge (only when the backend recommends a route), distance, drive time, arrival in
  local time, estimated miles at Low/Moderate/High/Severe/No Travel/Unknown, average score, weather coverage, eligibility and the ranking
  explanation. The four recommendation statuses are shown distinctly (`recommended`, `recommended_incomplete_weather`, `no_safe_route`,
  `insufficient_weather_data`) using the backend's own explanation text. Missing weather is shown as "No data" with the backend's reason, never as 0
  or as safe. Risk levels use text and a shape glyph as well as colour.
- **Map:** OpenStreetMap tiles (no key; see OSM's tile usage policy before heavy or production use). All candidate routes are drawn from the GeoJSON
  geometry (`[longitude, latitude]`, converted for Leaflet); click a line or a card to select one. A blue halo marks the recommended route and
  appears only when one exists. The selected route is drawn as a **risk corridor**: one coloured stretch per checkpoint (the same stretches the
  backend uses for risk miles), colourable by combined risk, wind, rain or snow, plus checkpoint markers with popups (mile, ETA, readings with units,
  hazard levels, load rule, missing-data reason). The table below lists every checkpoint, can filter to problem points, and locates a row on the map.
- **Forecast slider (0-48 h):** when a trip is submitted the app makes **one** request to the batch endpoint (below) for a bounded set of
  departures, every 6 hours from the entered departure (0, 6, ..., 48 h, nine in all). The server plans the routes once and fetches the weather once, so moving the slider to
  any of those offsets costs no further request. Other positions are assessed on release (debounced) as a batch of one, reusing the server's cached routes.
  Filled marks on the slider show exactly which departures have a real assessment; failed ones are marked and can be retried individually, and results
  older than 30 minutes are flagged and re-requested rather than shown as current. Nothing is interpolated or estimated in the browser. The "heatmap" is
  the risk corridor above: weather exists only at sampled checkpoints, so there is no interpolated field between them.

### Frontend limitations
- Only the nine prefetched departures are assessed up front; any other slider position is one more (cheap) request. The batch payload is large
  (about 1.5 MB, 270 KB gzipped, for nine departures) because every departure carries its checkpoints.
- No geocoding: coordinates only. Times are shown in the viewer's local time zone, which may differ from the trip's.
- The risk corridor colours the road around each sampled checkpoint; hazards between checkpoints can be missed (see Method limits above).
- Leaflet is not rendered in the jsdom tests, so map drawing is covered by the pure geometry tests plus a manual browser run.

### `POST /api/v1/routes/assess-batch/` (several departures, one trip)

Assesses the **same trip at several departure times** while planning the routes and fetching the weather once. It exists for the forecast slider;
`POST /api/v1/routes/assess/` is unchanged and still the endpoint for a single departure.

```json
{
  "origin": {"latitude": 34.0522, "longitude": -118.2437},
  "destination": {"latitude": 32.7767, "longitude": -96.7970},
  "departure_datetimes": ["2026-10-14T08:00:00-05:00", "2026-10-14T14:00:00-05:00", "2026-10-14T20:00:00-05:00"],
  "load_lb": 42000,
  "checkpoint_interval_miles": 25
}
```

Validation is the same as the single endpoint, plus: `departure_datetimes` is a non-empty list of **at most 12** timezone-aware, distinct (compared in UTC)
date-times; errors are keyed like `departure_datetimes.1`.

```json
{
  "api_version": "v1",
  "generated_at": "2026-10-12T18:35:00Z",
  "request": {"origin": {}, "destination": {}, "load_lb": 42000, "checkpoint_interval_miles": 25,
              "departure_datetimes": ["2026-10-14T13:00:00Z", "..."]},
  "units": {}, "risk_levels": [], "method": {"wind_metric": "sustained", "assumptions": [], "routing": {}, "weather": {}},
  "diagnostics": {"route_cache": "miss", "routing_provider_requests": 3, "weather_provider_requests": 4},
  "routes": [{"id": "route-1", "source": "baseline", "distance_miles": 1430.1, "duration_seconds": 119340, "geometry": {}}],
  "results": [
    {"index": 0, "departure_datetime": "2026-10-14T13:00:00Z", "departure_datetime_input": "2026-10-14T08:00:00-05:00", "ok": true,
     "recommendation": {"status": "recommended", "recommended_route_id": "route-1", "explanation": "..."},
     "notes": [], "routes": [{"id": "route-1", "rank": 1, "eligible": true, "risk_summary": {}, "checkpoints": []}]},
    {"index": 1, "departure_datetime": "...", "departure_datetime_input": "...", "ok": false,
     "error": {"code": "assessment_failed", "message": "This departure could not be assessed."}}
  ]
}
```

- `routes` holds each route's geometry **once** (GeoJSON `[longitude, latitude]`); each result's routes refer to it by `id` and are otherwise
  exactly what the single endpoint returns for that departure (same checkpoints, ETAs, weather, risk, coverage, eligibility, ranking and
  recommendation status), verified by tests that compare batch results with single-endpoint responses and by a live run.
- `results` come back in request order and identify their departure (`index`, `departure_datetime`, `departure_datetime_input`).
- **Failures:** routing failures or a failure of the shared weather fetch fail the whole request with the same errors as the single endpoint
  (422/502/503/504). A failure confined to one departure is reported on that result (`ok: false`) while the others are returned; if no
  departure can be assessed the request fails with 502 `assessment_failed`. Missing weather is reported per checkpoint exactly as before and
  never as safe.
- `diagnostics` states whether the planned routes came from the cache and how many provider HTTP requests this call made.

**Why reuse is safe.** The routes depend only on origin, destination and the routing provider's configuration: the OpenRouteService request
carries coordinates, snap radii and a preference, with no departure time, traffic or truck weight. So geometry and duration do not change
with departure, load or checkpoint interval. If routing ever starts using any of those, add them to `route_cache_key` in `backend/trips/batch.py`
and revisit the reuse. Weather is shared too: checkpoint coordinates are identical for every departure, so one Open-Meteo fetch over the union
time window serves all of them, and each departure is still assessed by the unchanged `assess_routes()`.

**Route cache.** Planned routes are kept in a small per-process in-memory cache (`CACHES["routes"]`, at most 20 entries) for
`ROUTE_CACHE_TTL_SECONDS` (default 900; `0` disables it). The key is a hash of origin, destination (6 decimals), routing provider, profile and
planner configuration. Only successful plans are stored; provider failures are never cached, and a broken cache backend falls back to planning
every time. The cache holds no user data. With several server processes each has its own cache (a cold process just plans again). The
single-departure endpoint does not use the cache.

**Measured effect** (real providers, LA to Dallas, 25-mile checkpoints; "submit, then move the slider to +6, +12, +24, +36 and +48 h"):

| | routing requests | weather requests |
| --- | --- | --- |
| before: 6 single-departure requests (each re-plans) | 18 | 24 |
| after: 1 batch of 9 departures (later offsets cached in the browser) | 3 | 4 |
| after, then a new offset such as +7 h | +0 (routes cached) | +4 |

Open-Meteo's free limit (600 calls/minute) appears to count each location, and one assessment sends about 175 locations; the old
approach would have sent about 1,050 locations for that interaction and the batch about 175. Bursts of several assessments within a minute can still
return a 503 `weather_rate_limited`, which is retryable.
