from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/upload/", views.upload_planilha, name="upload_planilha"),
]
