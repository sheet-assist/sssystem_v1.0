from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin

from .forms import FilterCriteriaForm
from .models import FilterCriteria
from .services import apply_filter_rule


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
    paginate_by = 20

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("state", "county")
            .prefetch_related("counties")
        )


class CriteriaCreateView(AdminRequiredMixin, CreateView):
    model = FilterCriteria
    form_class = FilterCriteriaForm
    template_name = "settings_app/criteria_form.html"
    success_url = reverse_lazy("settings_app:criteria_list")

    def form_valid(self, form):
        messages.success(self.request, "Filter rule created successfully.")
        return super().form_valid(form)


class CriteriaUpdateView(AdminRequiredMixin, UpdateView):
    model = FilterCriteria
    form_class = FilterCriteriaForm
    template_name = "settings_app/criteria_form.html"
    success_url = reverse_lazy("settings_app:criteria_list")

    def form_valid(self, form):
        messages.success(self.request, "Filter rule updated successfully.")
        return super().form_valid(form)


class CriteriaDeleteView(AdminRequiredMixin, DeleteView):
    model = FilterCriteria
    success_url = reverse_lazy("settings_app:criteria_list")
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, "Filter rule deleted successfully.")
        return super().delete(request, *args, **kwargs)


class CriteriaApplyView(AdminRequiredMixin, View):
    def post(self, request, pk):
        rule = get_object_or_404(FilterCriteria.objects.prefetch_related("counties"), pk=pk)
        summary = apply_filter_rule(rule, acting_user=request.user)
        processed = summary["processed"]
        updated = summary["updated"]
        qualified = summary["qualified"]
        disqualified = summary["disqualified"]
        messages.info(
            request,
            (
                f"Applied '{rule.name}' to {processed} prospect"
                f"{'s' if processed != 1 else ''}. "
                f"Updated {updated}, qualified {qualified}, disqualified {disqualified}."
            ),
        )
        return redirect("settings_app:criteria_edit", pk=rule.pk)
