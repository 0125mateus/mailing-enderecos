from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/upload/", views.upload_planilha, name="upload_planilha"),
    path(
        "api/maps/automation/",
        views.iniciar_maps_automation,
        name="iniciar_maps_automation",
    ),
    path(
        "api/maps/automation/<str:job_id>/",
        views.status_maps_automation,
        name="status_maps_automation",
    ),
    path(
        "api/maps/automation/<str:job_id>/cancelar/",
        views.cancelar_maps_automation,
        name="cancelar_maps_automation",
    ),
]
