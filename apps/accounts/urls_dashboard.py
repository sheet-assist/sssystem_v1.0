from django.urls import path

from . import views_dashboard

app_name = "dashboard"

urlpatterns = [
    path("", views_dashboard.DashboardView.as_view(), name="home"),
]
