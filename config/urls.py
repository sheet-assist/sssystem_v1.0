from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("dashboard/", include("apps.accounts.urls_dashboard")),
    path("accounts/", include("apps.accounts.urls")),
    path("prospects/", include("apps.prospects.urls")),
    path("cases/", include("apps.cases.urls")),
    path("scraper/", include("apps.scraper.urls")),
    path("settings/", include("apps.settings_app.urls")),
]
