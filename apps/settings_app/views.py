from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AdminRequiredMixin
from apps.prospects.forms import CSVUploadForm
from apps.prospects.services.csv_import import import_prospects_from_csv

from .forms import FilterCriteriaForm, SSRevenueTierForm, UserARSTierForm, SurplusThresholdForm
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
        setting = SSRevenueSetting.get_solo()
        ctx["ss_revenue_tier"] = setting.tier_percent
        ctx["ars_tier_percent"] = setting.ars_tier_percent
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
        User = get_user_model()
        
        setting = SSRevenueSetting.get_solo()
        ctx["current_tier"] = setting.tier_percent
        ctx["current_ars_tier"] = setting.ars_tier_percent
        ctx["form"] = SSRevenueTierForm(
            initial={
                "tier_percent": str(setting.tier_percent),
                "ars_tier_percent": str(setting.ars_tier_percent),
            }
        )
        ctx["tier_choices"] = SSRevenueSetting.TIER_CHOICES
        ctx["ars_tier_choices"] = SSRevenueSetting.ARS_TIER_CHOICES
        ctx["selected_tier"] = str(setting.tier_percent)
        ctx["selected_ars_tier"] = str(setting.ars_tier_percent)
        
        # Surplus threshold form
        ctx["surplus_threshold_form"] = SurplusThresholdForm(
            initial={
                "surplus_threshold_1": setting.surplus_threshold_1,
                "surplus_threshold_2": setting.surplus_threshold_2,
                "surplus_threshold_3": setting.surplus_threshold_3,
            }
        )
        ctx["surplus_thresholds"] = {
            "threshold_1": setting.surplus_threshold_1,
            "threshold_2": setting.surplus_threshold_2,
            "threshold_3": setting.surplus_threshold_3,
        }
        
        # User-specific ARS tiers
        ctx["user_ars_form"] = UserARSTierForm()
        users_with_tiers = User.objects.filter(
            profile__isnull=False
        ).select_related('profile').order_by('first_name', 'last_name')
        ctx["users_with_tiers"] = [
            {
                "user": user,
                "username": user.username,
                "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
                "ars_tier": user.profile.ars_tier_percent,
            }
            for user in users_with_tiers
        ]
        return ctx

    def post(self, request, *args, **kwargs):
        # Handle global tier settings
        if "tier_percent" in request.POST:
            form = SSRevenueTierForm(request.POST)
            if not form.is_valid():
                ctx = self.get_context_data(**kwargs)
                ctx["form"] = form
                ctx["tier_choices"] = SSRevenueSetting.TIER_CHOICES
                ctx["ars_tier_choices"] = SSRevenueSetting.ARS_TIER_CHOICES
                ctx["selected_tier"] = request.POST.get("tier_percent", "15")
                ctx["selected_ars_tier"] = request.POST.get("ars_tier_percent", "5")
                return self.render_to_response(ctx)

            setting = SSRevenueSetting.get_solo()
            setting.tier_percent = int(form.cleaned_data["tier_percent"])
            setting.ars_tier_percent = int(form.cleaned_data["ars_tier_percent"])
            setting.updated_by = request.user
            setting.save(update_fields=["tier_percent", "ars_tier_percent", "updated_by", "updated_at"])
            messages.success(
                request,
                (
                    f"SS Revenue Tier updated to {setting.tier_percent}% "
                    f"and ARS Tier updated to {setting.ars_tier_percent}%."
                ),
            )
            return redirect("settings_app:finance")
        
        # Handle user-specific ARS tier settings
        elif "user" in request.POST:
            form = UserARSTierForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data["user"]
                ars_tier = int(form.cleaned_data["ars_tier_percent"])
                user.profile.ars_tier_percent = ars_tier
                user.profile.save(update_fields=["ars_tier_percent"])
                messages.success(
                    request,
                    f"ARS Tier for {user.get_full_name() or user.username} updated to {ars_tier}%."
                )
            else:
                # Show form errors
                error_msg = " ".join([str(e) for errors in form.errors.values() for e in errors])
                messages.error(request, f"Error updating user ARS tier: {error_msg}")
            return redirect("settings_app:finance")
        
        # Handle surplus threshold settings
        elif "surplus_threshold_1" in request.POST:
            form = SurplusThresholdForm(request.POST)
            if form.is_valid():
                setting = SSRevenueSetting.get_solo()
                setting.surplus_threshold_1 = form.cleaned_data["surplus_threshold_1"]
                setting.surplus_threshold_2 = form.cleaned_data["surplus_threshold_2"]
                setting.surplus_threshold_3 = form.cleaned_data["surplus_threshold_3"]
                setting.updated_by = request.user
                setting.save(update_fields=["surplus_threshold_1", "surplus_threshold_2", "surplus_threshold_3", "updated_by", "updated_at"])
                messages.success(
                    request,
                    f"Surplus filter thresholds updated to ${setting.surplus_threshold_1:,.0f}, "
                    f"${setting.surplus_threshold_2:,.0f}, and ${setting.surplus_threshold_3:,.0f}."
                )
            else:
                # Show form errors
                error_msg = " ".join([str(e) for errors in form.errors.values() for e in errors])
                messages.error(request, f"Error updating surplus thresholds: {error_msg}")
            return redirect("settings_app:finance")


class CSVUploadView(AdminRequiredMixin, TemplateView):
    template_name = "settings_app/prospect_csv_upload.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", CSVUploadForm())
        return ctx

    def post(self, request, *args, **kwargs):
        form = CSVUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        county = form.cleaned_data["county"]
        csv_file = form.cleaned_data["csv_file"]

        result = import_prospects_from_csv(csv_file, county, request.user)

        if result["errors"] and result["created"] == 0 and result["skipped"] == 0:
            for err in result["errors"][:10]:
                messages.error(request, err["message"])
        else:
            summary_parts = []
            if result["created"]:
                summary_parts.append(f"{result['created']} prospect(s) created")
            if result["skipped"]:
                summary_parts.append(f"{result['skipped']} duplicate(s) skipped")
            if result["errors"]:
                summary_parts.append(f"{len(result['errors'])} row error(s)")

            messages.success(request, f"CSV upload complete: {', '.join(summary_parts)}.")

            for err in result["errors"][:10]:
                messages.warning(request, err["message"])

        return redirect("settings_app:prospect_csv_upload")
