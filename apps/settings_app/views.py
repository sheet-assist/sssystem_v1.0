from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin

from .forms import FilterCriteriaForm
from .models import FilterCriteria


class SettingsHomeView(AdminRequiredMixin, TemplateView):
    template_name = "settings_app/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["criteria_count"] = FilterCriteria.objects.filter(is_active=True).count()
        return ctx


class CriteriaListView(AdminRequiredMixin, ListView):
    model = FilterCriteria
    template_name = "settings_app/criteria_list.html"
    context_object_name = "criteria"


class CriteriaCreateView(AdminRequiredMixin, CreateView):
    model = FilterCriteria
    form_class = FilterCriteriaForm
    template_name = "settings_app/criteria_form.html"
    success_url = reverse_lazy("settings_app:criteria_list")

    def form_valid(self, form):
        messages.success(self.request, "Filter rule created.")
        return super().form_valid(form)


class CriteriaUpdateView(AdminRequiredMixin, UpdateView):
    model = FilterCriteria
    form_class = FilterCriteriaForm
    template_name = "settings_app/criteria_form.html"
    success_url = reverse_lazy("settings_app:criteria_list")

    def form_valid(self, form):
        messages.success(self.request, "Filter rule updated.")
        return super().form_valid(form)
