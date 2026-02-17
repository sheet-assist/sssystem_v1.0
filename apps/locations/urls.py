from django.urls import path
from . import views

app_name = "locations"

urlpatterns = [
    # County Management
    path('counties/', views.CountyListView.as_view(), name='county_list'),
    path('counties/create/', views.CountyCreateView.as_view(), name='county_create'),
    path('counties/<int:pk>/', views.CountyUpdateView.as_view(), name='county_detail'),
    path('counties/<int:pk>/config/', views.CountyConfigView.as_view(), name='county_config'),
    path('counties/<int:pk>/delete/', views.CountyDeleteView.as_view(), name='county_delete'),
]

