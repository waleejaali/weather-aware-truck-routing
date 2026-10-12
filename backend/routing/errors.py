"""Routing errors. Provider adapters translate their own failures into these."""


class RoutingError(Exception):
    """Base class for all routing failures."""


class RoutingProviderError(RoutingError):
    """The routing provider failed or returned something unusable."""


class ProviderConfigurationError(RoutingProviderError):
    """Provider credentials or settings are missing or invalid."""


class ProviderAuthError(RoutingProviderError):
    """The provider rejected the credentials (HTTP 401/403)."""


class ProviderRateLimitError(RoutingProviderError):
    """The provider quota or rate limit was hit (HTTP 429)."""


class ProviderTimeoutError(RoutingProviderError):
    """The provider did not answer in time."""


class ProviderConnectionError(RoutingProviderError):
    """The provider could not be reached."""


class ProviderResponseError(RoutingProviderError):
    """The provider answered with a malformed or incomplete payload."""


class ProviderRequestError(RoutingProviderError):
    """The provider rejected the request (other 4xx/5xx)."""

    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AlternativeRoutesUnavailable(ProviderRequestError):
    """The provider cannot compute alternative routes for this request (e.g. distance limit)."""


class NoRouteFound(ProviderRequestError):
    """The provider could not find a route between the given points."""


class NoRoutesFoundError(RoutingError):
    """No valid route could be produced for the trip."""
