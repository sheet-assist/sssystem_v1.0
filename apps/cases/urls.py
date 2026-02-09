from django.urls import path
from django.views.generic import TemplateView

app_name = "cases"

urlpatterns = [
    path("", TemplateView.as_view(template_name="cases/list.html"), name="list"),
]
