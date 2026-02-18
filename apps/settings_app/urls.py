from django.urls import path

from . import views

app_name = "settings_app"

urlpatterns = [
    path("", views.SettingsHomeView.as_view(), name="home"),
    path("finance/", views.FinanceSettingsView.as_view(), name="finance"),
    path("criteria/", views.CriteriaListView.as_view(), name="criteria_list"),
    path("criteria/add/", views.CriteriaCreateView.as_view(), name="criteria_add"),
    path("criteria/<int:pk>/edit/", views.CriteriaUpdateView.as_view(), name="criteria_edit"),
    path("criteria/<int:pk>/delete/", views.CriteriaDeleteView.as_view(), name="criteria_delete"),
    path("criteria/<int:pk>/apply/", views.CriteriaApplyView.as_view(), name="criteria_apply"),
    path("prospects/upload-csv/", views.CSVUploadView.as_view(), name="prospect_csv_upload"),
    path("prospects/uploads/", views.UploadListView.as_view(), name="prospect_upload_list"),
    path("prospects/uploads/<int:pk>/prospects/", views.UploadProspectsListView.as_view(), name="prospect_upload_prospects"),
    path("prospects/uploads/<int:pk>/apply-rule/", views.ApplyRuleToUploadView.as_view(), name="prospect_upload_apply_rule"),
]
