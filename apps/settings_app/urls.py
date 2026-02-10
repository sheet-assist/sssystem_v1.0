from django.urls import path

from . import views

app_name = "settings_app"

urlpatterns = [
    path("", views.SettingsHomeView.as_view(), name="home"),
    path("criteria/", views.CriteriaListView.as_view(), name="criteria_list"),
    path("criteria/add/", views.CriteriaCreateView.as_view(), name="criteria_add"),
    path("criteria/<int:pk>/edit/", views.CriteriaUpdateView.as_view(), name="criteria_edit"),
    path("criteria/<int:pk>/delete/", views.CriteriaDeleteView.as_view(), name="criteria_delete"),
]
