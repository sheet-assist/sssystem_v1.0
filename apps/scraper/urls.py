from django.urls import path
from django.views.generic import TemplateView

app_name = "scraper"

urlpatterns = [
    path("dashboard/", TemplateView.as_view(template_name="scraper/dashboard.html"), name="dashboard"),
]
