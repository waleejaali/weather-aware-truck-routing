class WeatherProviderError(Exception):
    pass


class WeatherTimeoutError(WeatherProviderError):
    pass


class WeatherConnectionError(WeatherProviderError):
    pass


class WeatherRateLimitError(WeatherProviderError):
    pass


class WeatherRequestError(WeatherProviderError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class WeatherResponseError(WeatherProviderError):
    """Malformed payload, or units we didn't ask for."""
