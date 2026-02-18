from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView
from django.db.models import Q

from apps.accounts.mixins import CasesAccessMixin
from apps.locations.models import State
from apps.prospects.models import Prospect, log_prospect_action

from .forms import CaseFollowUpForm, CaseNoteForm, CaseStatusForm, ConvertToCaseForm
from .models import Case, CaseFollowUp, CaseNote, log_case_action

User = get_user_model()


class CaseListView(CasesAccessMixin, ListView):
    model = Case
    template_name = "cases/list.html"
    paginate_by = 25

    def get_queryset(self):
        qs = Case.objects.select_related("county", "county__state", "assigned_to", "prospect")
        
        case_type = self.request.GET.get("case_type")
        status = self.request.GET.get("status")
        county = self.request.GET.get("county", "").strip()
        state = self.request.GET.get("state", "").strip()
        case_number = self.request.GET.get("case_number", "").strip()
        
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        
        # Search by case number
        if case_number:
            qs = qs.filter(case_number__icontains=case_number)
        
        # Search by county name
        if county:
            qs = qs.filter(county__name__icontains=county)
        
        # Search by state name or abbreviation
        if state:
            qs = qs.filter(Q(county__state__name__icontains=state) | Q(county__state__abbreviation__icontains=state))
        
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["case_types"] = Case.CASE_TYPE_CHOICES
        ctx["statuses"] = Case.CASE_STATUS
        ctx["current_type"] = self.request.GET.get("case_type", "")
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["case_number_search"] = self.request.GET.get("case_number", "")
        ctx["county_search"] = self.request.GET.get("county", "")
        ctx["state_search"] = self.request.GET.get("state", "")
        ctx["states"] = State.objects.filter(is_active=True).order_by("name")
        return ctx


class CaseDetailView(CasesAccessMixin, DetailView):
    model = Case
    template_name = "cases/detail.html"

    def get_queryset(self):
        return Case.objects.select_related(
            "county", "county__state", "assigned_to",
            "prospect", "prospect__assigned_to", "prospect__assigned_by",
        ).prefetch_related(
            "notes__author",
            "followups__assigned_to",
            "action_logs__user",
            "prospect__action_logs__user",
        )

    def get_context_data(self, **kwargs):
        from apps.prospects.views import _build_lifecycle_timeline
        ctx = super().get_context_data(**kwargs)
        ctx["timeline"] = _build_lifecycle_timeline(self.object.prospect)
        return ctx


class ConvertProspectToCaseView(CasesAccessMixin, FormView):
    template_name = "cases/convert.html"
    form_class = ConvertToCaseForm

    def dispatch(self, request, *args, **kwargs):
        self.prospect = get_object_or_404(Prospect, pk=self.kwargs["pk"])
        if hasattr(self.prospect, "case"):
            messages.warning(request, "This prospect has already been converted to a case.")
            return redirect("prospects:detail", pk=self.prospect.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect"] = self.prospect
        return ctx

    def form_valid(self, form):
        p = self.prospect
        case = Case.objects.create(
            prospect=p,
            case_type=p.prospect_type,
            county=p.county,
            assigned_to=p.assigned_to,
            property_address=p.property_address,
            case_number=p.case_number,
            parcel_id=p.parcel_id,
            contract_date=form.cleaned_data.get("contract_date"),
            contract_notes=form.cleaned_data.get("contract_notes", ""),
        )
        p.workflow_status = "converted"
        p.save()
        log_prospect_action(p, self.request.user, "converted_to_case", f"Converted to Case #{case.pk}")
        log_case_action(case, self.request.user, "created", f"Created from Prospect #{p.pk}")
        messages.success(self.request, f"Case #{case.pk} created from prospect.")
        return redirect("cases:detail", pk=case.pk)


class CaseNoteCreateView(CasesAccessMixin, CreateView):
    model = CaseNote
    form_class = CaseNoteForm
    template_name = "cases/note_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.case_obj = get_object_or_404(Case, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["case"] = self.case_obj
        return ctx

    def form_valid(self, form):
        form.instance.case = self.case_obj
        form.instance.author = self.request.user
        resp = super().form_valid(form)
        log_case_action(self.case_obj, self.request.user, "note_added", "Note added")
        messages.success(self.request, "Note added.")
        return resp

    def get_success_url(self):
        return reverse("cases:detail", kwargs={"pk": self.case_obj.pk})


class CaseFollowUpCreateView(CasesAccessMixin, CreateView):
    model = CaseFollowUp
    form_class = CaseFollowUpForm
    template_name = "cases/followup_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.case_obj = get_object_or_404(Case, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["case"] = self.case_obj
        return ctx

    def form_valid(self, form):
        form.instance.case = self.case_obj
        resp = super().form_valid(form)
        log_case_action(self.case_obj, self.request.user, "followup_created", f"Follow-up due {form.instance.due_date}")
        messages.success(self.request, "Follow-up created.")
        return resp

    def get_success_url(self):
        return reverse("cases:detail", kwargs={"pk": self.case_obj.pk})


class CaseFollowUpCompleteView(CasesAccessMixin, FormView):
    """Mark a follow-up as completed."""
    form_class = CaseStatusForm  # dummy — we only need POST

    def post(self, request, *args, **kwargs):
        followup = get_object_or_404(CaseFollowUp, pk=self.kwargs["followup_pk"])
        followup.is_completed = True
        followup.completed_at = timezone.now()
        followup.save()
        log_case_action(followup.case, request.user, "followup_completed", f"Follow-up #{followup.pk} completed")
        messages.success(request, "Follow-up marked as completed.")
        return redirect("cases:detail", pk=followup.case.pk)


class CaseStatusUpdateView(CasesAccessMixin, FormView):
    template_name = "cases/status_update.html"
    form_class = CaseStatusForm

    def dispatch(self, request, *args, **kwargs):
        self.case_obj = get_object_or_404(Case, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"status": self.case_obj.status}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["case"] = self.case_obj
        return ctx

    def form_valid(self, form):
        old = self.case_obj.status
        new = form.cleaned_data["status"]
        self.case_obj.status = new
        self.case_obj.save()
        log_case_action(self.case_obj, self.request.user, "status_changed", f"Status: {old} → {new}")
        messages.success(self.request, f"Case status updated to {new}.")
        return redirect("cases:detail", pk=self.case_obj.pk)


class CaseHistoryView(CasesAccessMixin, DetailView):
    model = Case
    template_name = "cases/history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = self.object.action_logs.select_related("user").all()
        return ctx


class CaseAutodialerView(CasesAccessMixin, DetailView):
    model = Case
    template_name = "cases/autodialer.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["phone_numbers"] = []
        return ctx


class CaseEmailView(CasesAccessMixin, DetailView):
    model = Case
    template_name = "cases/email_send.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["email_addresses"] = []
        return ctx
