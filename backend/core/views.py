from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(request):
    """Liveness check used by the frontend to confirm the backend is reachable."""
    return Response({"status": "ok", "service": "weather-aware-truck-routing"})
