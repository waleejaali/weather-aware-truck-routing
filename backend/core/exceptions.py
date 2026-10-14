from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

_CODES = {
    exceptions.ParseError: ("invalid_json", "The request body is not valid JSON."),
    exceptions.UnsupportedMediaType: ("unsupported_media_type", "Send the request as application/json."),
    exceptions.MethodNotAllowed: ("method_not_allowed", "This method is not allowed on this endpoint."),
    exceptions.NotFound: ("not_found", "Not found."),
}


def error_response(code: str, message: str, status: int, fields: dict | None = None) -> Response:
    body: dict = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return Response({"error": body}, status=status)


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    code, message = _CODES.get(type(exc), ("request_error", "The request could not be processed."))
    return error_response(code, message, response.status_code)


def flatten_errors(errors, prefix: str = "") -> dict[str, list[str]]:
    """{'origin': {'latitude': ['x']}} -> {'origin.latitude': ['x']}."""
    flat: dict[str, list[str]] = {}
    for key, value in errors.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if key == "non_field_errors" and prefix == "":
            path = "body"
        if isinstance(value, dict):
            flat.update(flatten_errors(value, path))
        else:
            flat[path] = [str(item) for item in (value if isinstance(value, list) else [value])]
    return flat
