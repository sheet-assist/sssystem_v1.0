from django.urls import path

from . import views

app_name = "scraper"

urlpatterns = [
    path("dashboard/", views.ScraperDashboardView.as_view(), name="dashboard"),
    path("jobs/", views.ScrapeJobListView.as_view(), name="job_list"),
    path("jobs/create/", views.ScrapeJobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/", views.ScrapeJobDetailView.as_view(), name="job_detail"),
    path("jobs/<int:pk>/run/", views.ScrapeJobRunView.as_view(), name="job_run"),
]
