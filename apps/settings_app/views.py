from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin

from .forms import FilterCriteriaForm, SSRevenueTierForm
from .models import FilterCriteria, SSRevenueSetting
from .services import apply_filter_rule


class FinanceSettingsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return hasattr(user, "profile") and (
            user.profile.is_admin or user.profile.can_manage_finance_settings
        )


class SettingsHomeView(AdminRequiredMixin, TemplateView):
    template_name = "settings_app/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["criteria_count"] = FilterCriteria.objects.filter(is_active=True).count()
        ctx["ss_revenue_tier"] = SSRevenueSetting.get_solo().tier_percent
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


class FinanceSettingsView(FinanceSettingsAccessMixin, TemplateView):
    template_name = "settings_app/finance.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        setting = SSRevenueSetting.get_solo()
        ctx["current_tier"] = setting.tier_percent
        ctx["form"] = SSRevenueTierForm(initial={"tier_percent": str(setting.tier_percent)})
        ctx["tier_choices"] = SSRevenueSetting.TIER_CHOICES
        ctx["selected_tier"] = str(setting.tier_percent)
        return ctx

    def post(self, request, *args, **kwargs):
        form = SSRevenueTierForm(request.POST)
        if not form.is_valid():
            ctx = self.get_context_data(**kwargs)
            ctx["form"] = form
            ctx["tier_choices"] = SSRevenueSetting.TIER_CHOICES
            ctx["selected_tier"] = request.POST.get("tier_percent", "15")
            return self.render_to_response(ctx)

        setting = SSRevenueSetting.get_solo()
        setting.tier_percent = int(form.cleaned_data["tier_percent"])
        setting.updated_by = request.user
        setting.save(update_fields=["tier_percent", "updated_by", "updated_at"])
        messages.success(request, f"SS Revenue Tier updated to {setting.tier_percent}%.")
        return redirect("settings_app:finance")
