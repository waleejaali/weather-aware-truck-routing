import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

# One .env at the repo root, shared with the frontend.
load_dotenv(REPO_ROOT / ".env")


def _env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("1", "true", "yes")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not true.")

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Vercel injects this deployment's own hostnames, so the API answers on its generated URLs
# without listing them by hand. A custom domain still goes in DJANGO_ALLOWED_HOSTS.
ALLOWED_HOSTS += [
    host
    for host in (os.environ.get(name, "") for name in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"))
    if host
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "core",
    "routing",
    "weather",
    "risk",
    "trips",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # route geometries are big; gzip shrinks them ~5-10x
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {}

CORS_ALLOWED_ORIGINS = _env_list("FRONTEND_URL", "http://localhost:5173")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
ORS_BASE_URL = os.environ.get("ORS_BASE_URL", "https://api.openrouteservice.org")
ORS_PROFILE = os.environ.get("ORS_PROFILE", "driving-hgv")
ORS_TIMEOUT_SECONDS = float(os.environ.get("ORS_TIMEOUT_SECONDS", "30"))
OPEN_METEO_BASE_URL = os.environ.get("OPEN_METEO_BASE_URL", "https://api.open-meteo.com")
WEATHER_TIMEOUT_SECONDS = float(os.environ.get("WEATHER_TIMEOUT_SECONDS", "20"))
WEATHER_WIND_METRIC = os.environ.get("WEATHER_WIND_METRIC", "sustained")  # "sustained" or "gust"

ROUTE_CACHE_TTL_SECONDS = int(os.environ.get("ROUTE_CACHE_TTL_SECONDS", "900"))  # 0 disables the cache
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "routes": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "planned-routes",
        "OPTIONS": {"MAX_ENTRIES": 20},  # entries hold full geometries, so keep this small
    },
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
