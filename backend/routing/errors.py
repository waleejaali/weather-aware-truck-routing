class RoutingError(Exception):
    pass


class RoutingProviderError(RoutingError):
    pass


class ProviderConfigurationError(RoutingProviderError):
    pass


class ProviderAuthError(RoutingProviderError):
    pass


class ProviderRateLimitError(RoutingProviderError):
    pass


class ProviderTimeoutError(RoutingProviderError):
    pass


class ProviderConnectionError(RoutingProviderError):
    pass


class ProviderResponseError(RoutingProviderError):
    pass


class ProviderRequestError(RoutingProviderError):
    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AlternativeRoutesUnavailable(ProviderRequestError):
    """E.g. the trip is over the provider's distance limit for alternatives."""


class NoRouteFound(ProviderRequestError):
    """The provider found no road connection between the points."""


class NoRoutesFoundError(RoutingError):
    """The planner couldn't produce any valid route (after validation and fallbacks)."""
