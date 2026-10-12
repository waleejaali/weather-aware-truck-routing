"""Routing provider adapters. Use get_routing_provider() rather than importing a concrete adapter."""

from django.conf import settings

from .base import RoutingProvider
from .ors import OpenRouteServiceProvider


def get_routing_provider() -> RoutingProvider:
    """Build the configured provider from Django settings (ORS_* environment variables)."""
    return OpenRouteServiceProvider(
        settings.ORS_API_KEY,
        base_url=settings.ORS_BASE_URL,
        profile=settings.ORS_PROFILE,
        timeout_s=settings.ORS_TIMEOUT_SECONDS,
    )
