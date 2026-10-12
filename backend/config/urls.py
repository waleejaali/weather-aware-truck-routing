from django.urls import include, path

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/v1/", include("trips.urls")),
]
