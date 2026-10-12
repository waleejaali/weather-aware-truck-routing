from django.urls import path

from . import views

urlpatterns = [
    path("routes/assess/", views.AssessRoutesView.as_view(), name="assess-routes"),
]
