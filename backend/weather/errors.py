"""Weather errors. Provider adapters translate their own failures into these."""


class WeatherProviderError(Exception):
    """The weather provider failed or returned something unusable."""


class WeatherTimeoutError(WeatherProviderError):
    """The provider did not answer in time."""


class WeatherConnectionError(WeatherProviderError):
    """The provider could not be reached."""


class WeatherRateLimitError(WeatherProviderError):
    """The provider's rate limit or quota was hit (HTTP 429)."""


class WeatherRequestError(WeatherProviderError):
    """The provider rejected the request (4xx/5xx), with its stated reason when given."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class WeatherResponseError(WeatherProviderError):
    """The provider answered with a malformed, inconsistent or unexpectedly-unit-ed payload."""
