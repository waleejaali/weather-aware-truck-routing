# Weather-Aware Truck Routing

Compare three driving routes for a truck based on weather along the route, load weight, estimated checkpoint arrival times, and travel duration.

> **Status:** foundation plus the routing layer (backend service and live-test command). No API endpoint, weather retrieval, risk calculation or map UI yet.

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
  risk/        Pure risk classification and route ranking (no Django/network imports)
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
| `OPEN_METEO_BASE_URL` | backend | Weather provider (not used yet) |
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
