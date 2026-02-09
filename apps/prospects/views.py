from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView
from django_filters.views import FilterView

from apps.accounts.mixins import AdminRequiredMixin, ProspectsAccessMixin
from apps.locations.models import County, State

from .filters import ProspectFilter
from .forms import AssignProspectForm, ProspectNoteForm, ResearchForm, WorkflowTransitionForm
from .models import Prospect, ProspectNote, log_prospect_action

User = get_user_model()


# --- Phase 5: Navigation Flow ---

class TypeSelectView(ProspectsAccessMixin, TemplateView):
    template_name = "prospects/type_select.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["types"] = Prospect.PROSPECT_TYPES
        return ctx


class StateSelectView(ProspectsAccessMixin, ListView):
    template_name = "prospects/state_select.html"
    context_object_name = "states"

    def get_queryset(self):
        return State.objects.filter(is_active=True, counties__is_active=True).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs["type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["type"], "")
        return ctx


class CountySelectView(ProspectsAccessMixin, ListView):
    template_name = "prospects/county_select.html"
    context_object_name = "counties"

    def get_queryset(self):
        return County.objects.filter(
            state__abbreviation__iexact=self.kwargs["state"],
            is_active=True,
        ).select_related("state")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs["type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["type"], "")
        ctx["state_abbr"] = self.kwargs["state"].upper()
        return ctx


class ProspectListView(ProspectsAccessMixin, FilterView):
    model = Prospect
    template_name = "prospects/list.html"
    filterset_class = ProspectFilter
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("county", "county__state", "assigned_to")
        ptype = self.kwargs.get("type")
        state = self.kwargs.get("state")
        county_slug = self.kwargs.get("county")
        if ptype:
            qs = qs.filter(prospect_type=ptype)
        if state:
            qs = qs.filter(county__state__abbreviation__iexact=state)
        if county_slug:
            qs = qs.filter(county__slug=county_slug)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs.get("type", "")
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs.get("type", ""), "")
        ctx["state_abbr"] = self.kwargs.get("state", "")
        ctx["county_slug"] = self.kwargs.get("county", "")
        if self.kwargs.get("county"):
            ctx["county_obj"] = County.objects.filter(slug=self.kwargs["county"]).first()
        return ctx


class ProspectDetailView(ProspectsAccessMixin, DetailView):
    model = Prospect
    template_name = "prospects/detail.html"

    def get_queryset(self):
        return Prospect.objects.select_related(
            "county", "county__state", "assigned_to", "assigned_by"
        ).prefetch_related("notes__author", "action_logs__user")


# --- Phase 5: Qualification Buckets ---

class QualifiedListView(ProspectListView):
    def get_queryset(self):
        return super().get_queryset().filter(qualification_status="qualified")


class DisqualifiedListView(ProspectListView):
    def get_queryset(self):
        return super().get_queryset().filter(qualification_status="disqualified")


class PendingListView(ProspectListView):
    def get_queryset(self):
        return super().get_queryset().filter(qualification_status="pending")


# --- Phase 6: Assignment, Notes, Workflow ---

class MyProspectsView(ProspectsAccessMixin, FilterView):
    model = Prospect
    template_name = "prospects/list.html"
    filterset_class = ProspectFilter
    paginate_by = 25

    def get_queryset(self):
        return Prospect.objects.filter(
            assigned_to=self.request.user
        ).select_related("county", "county__state", "assigned_to")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "My Prospects"
        return ctx


class AssignProspectView(AdminRequiredMixin, FormView):
    template_name = "prospects/assign.html"
    form_class = AssignProspectForm

    def dispatch(self, request, *args, **kwargs):
        self.prospect = get_object_or_404(Prospect, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect"] = self.prospect
        return ctx

    def form_valid(self, form):
        user = form.cleaned_data["assigned_to"]
        self.prospect.assigned_to = user
        self.prospect.assigned_by = self.request.user
        self.prospect.assigned_at = timezone.now()
        if self.prospect.workflow_status == "new":
            self.prospect.workflow_status = "assigned"
        self.prospect.save()
        log_prospect_action(self.prospect, self.request.user, "assigned", f"Assigned to {user.username}")
        messages.success(self.request, f"Prospect assigned to {user.username}.")
        return redirect("prospects:detail", pk=self.prospect.pk)


class ProspectNoteCreateView(ProspectsAccessMixin, CreateView):
    model = ProspectNote
    form_class = ProspectNoteForm
    template_name = "prospects/note_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.prospect = get_object_or_404(Prospect, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect"] = self.prospect
        return ctx

    def form_valid(self, form):
        form.instance.prospect = self.prospect
        form.instance.author = self.request.user
        resp = super().form_valid(form)
        log_prospect_action(self.prospect, self.request.user, "note_added", "Note added")
        messages.success(self.request, "Note added.")
        return resp

    def get_success_url(self):
        return reverse("prospects:detail", kwargs={"pk": self.prospect.pk})


class ResearchUpdateView(ProspectsAccessMixin, FormView):
    template_name = "prospects/research_form.html"
    form_class = ResearchForm

    def dispatch(self, request, *args, **kwargs):
        self.prospect = get_object_or_404(Prospect, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        p = self.prospect
        return {
            "lien_check_done": p.lien_check_done,
            "lien_check_notes": p.lien_check_notes,
            "surplus_verified": p.surplus_verified,
            "documents_verified": p.documents_verified,
            "skip_trace_done": p.skip_trace_done,
            "owner_contact_info": p.owner_contact_info,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect"] = self.prospect
        return ctx

    def form_valid(self, form):
        for field, val in form.cleaned_data.items():
            setattr(self.prospect, field, val)
        self.prospect.save()
        log_prospect_action(self.prospect, self.request.user, "updated", "Research fields updated")
        messages.success(self.request, "Research fields updated.")
        return redirect("prospects:detail", pk=self.prospect.pk)


class WorkflowTransitionView(ProspectsAccessMixin, FormView):
    template_name = "prospects/transition.html"
    form_class = WorkflowTransitionForm

    def dispatch(self, request, *args, **kwargs):
        self.prospect = get_object_or_404(Prospect, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect"] = self.prospect
        return ctx

    def form_valid(self, form):
        new_status = form.cleaned_data["workflow_status"]
        old = self.prospect.workflow_status
        self.prospect.workflow_status = new_status
        self.prospect.save()
        log_prospect_action(
            self.prospect, self.request.user, "status_changed",
            f"Workflow: {old} → {new_status}"
        )
        messages.success(self.request, f"Status updated to {new_status}.")
        return redirect("prospects:detail", pk=self.prospect.pk)


class ProspectHistoryView(ProspectsAccessMixin, DetailView):
    model = Prospect
    template_name = "prospects/history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = self.object.action_logs.select_related("user").all()
        return ctx
