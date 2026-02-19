from django.urls import path

from . import views_dashboard

app_name = "dashboard"

urlpatterns = [
    path("", views_dashboard.DashboardView.as_view(), name="home"),
    path("api/daily-qualified/", views_dashboard.DailyQualifiedChartAPI.as_view(), name="daily_qualified_api"),
    path("api/cards-stats/", views_dashboard.DashboardCardsStatsAPI.as_view(), name="cards_stats_api"),
]
