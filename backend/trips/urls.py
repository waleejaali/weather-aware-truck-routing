from django.urls import path

from . import views

urlpatterns = [
    path("routes/assess/", views.AssessRoutesView.as_view(), name="assess-routes"),
    path("routes/assess-batch/", views.AssessBatchView.as_view(), name="assess-routes-batch"),
]
