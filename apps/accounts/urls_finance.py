from django.urls import path

from . import views_finance

app_name = "finance"

urlpatterns = [
    path("", views_finance.FinanceDashboardView.as_view(), name="dashboard"),
    path("api/data/", views_finance.FinanceDataAPI.as_view(), name="data_api"),
    path("api/counties/", views_finance.FinanceCountiesAPI.as_view(), name="counties_api"),
]
