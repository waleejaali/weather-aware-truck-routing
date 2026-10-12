# Weather-Aware Truck Routing

Compare three driving routes for a truck based on weather along the route, load weight, estimated checkpoint arrival times, and travel duration.

> **Status:** project foundation only. Routing, weather retrieval, risk calculation and the map UI are not implemented yet.

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
  routing/     Route generation and checkpoint sampling (providers/ = API adapters, services/ = logic)
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
| `ORS_API_KEY`, `ORS_BASE_URL` | backend | Routing provider (not used yet) |
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
