from django.conf import settings

from .base import WeatherProvider
from .open_meteo import OpenMeteoProvider


def get_weather_provider() -> WeatherProvider:
    return OpenMeteoProvider(
        base_url=settings.OPEN_METEO_BASE_URL,
        timeout_s=settings.WEATHER_TIMEOUT_SECONDS,
    )
