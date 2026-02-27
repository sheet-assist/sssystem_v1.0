import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.mixins import CasesAccessMixin
from apps.locations.models import State
from apps.prospects.models import Prospect, log_prospect_action

from .forms import CaseFollowUpForm, CaseNoteForm, CaseStatusForm, ConvertToCaseForm
from .models import Case, CaseDocument, CaseFollowUp, CaseNote, log_case_action

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

        qs = self.object_list
        ctx["stats_total"] = qs.count()
        ctx["stats_active"] = qs.filter(status="active").count()
        ctx["stats_closed_won"] = qs.filter(status="closed_won").count()
        ctx["stats_first_contract"] = (
            qs.filter(contract_date__isnull=False)
            .order_by("contract_date")
            .values_list("contract_date", flat=True)
            .first()
        )
        ctx["stats_last_contract"] = (
            qs.filter(contract_date__isnull=False)
            .order_by("-contract_date")
            .values_list("contract_date", flat=True)
            .first()
        )
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
            "prospect__tdm_documents",
            "documents__uploaded_by",
            "documents__notes__created_by",
        )

    def get_context_data(self, **kwargs):
        from apps.prospects.views import _build_lifecycle_timeline
        ctx = super().get_context_data(**kwargs)
        ctx["timeline"] = _build_lifecycle_timeline(self.object.prospect)
        if self.object.prospect:
            from django.db.models import Max
            ctx["tdm_downloaded_docs"] = self.object.prospect.tdm_documents.filter(is_downloaded=True)
            ctx["tdm_last_sync"] = self.object.prospect.tdm_documents.aggregate(Max("last_checked_at"))["last_checked_at__max"]
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


class CaseDocumentsPageView(CasesAccessMixin, DetailView):
    """Dedicated Digital Folder page for a Case (opens in new tab).

    Shows three sections:
    - Case Documents   (CaseDocument — full upload/delete/notes)
    - Prospect Documents (ProspectDocument — read-only list + upload via prospect endpoints)
    - TDM Scraped Documents (ProspectTDMDocument — with on-demand Sync button)
    """
    model = Case
    template_name = "cases/documents_page.html"

    def get_queryset(self):
        return Case.objects.select_related(
            "prospect", "prospect__county", "prospect__county__state",
        ).prefetch_related(
            "documents__uploaded_by",
            "documents__notes__created_by",
            "prospect__documents__uploaded_by",
            "prospect__documents__notes__created_by",
            "prospect__tdm_documents",
        )

    def get_context_data(self, **kwargs):
        from django.db.models import Max
        ctx = super().get_context_data(**kwargs)
        prospect = self.object.prospect
        if prospect:
            ctx["prospect_docs"] = prospect.documents.all().select_related(
                "uploaded_by"
            ).prefetch_related("notes__created_by")
            ctx["all_tdm"] = prospect.tdm_documents.all()
            ctx["tdm_last_sync"] = prospect.tdm_documents.aggregate(
                Max("last_checked_at")
            )["last_checked_at__max"]
        else:
            ctx["prospect_docs"] = []
            ctx["all_tdm"] = []
            ctx["tdm_last_sync"] = None
        return ctx


# -------------------- Digital Folder endpoints --------------------

def _user_can_modify_case_documents(user, case):
    if not hasattr(user, "profile"):
        return False
    return user.profile.is_admin or (case.assigned_to and case.assigned_to == user)


@login_required
@require_http_methods(["GET"])
def case_documents_list_v2(request, pk):
    case = get_object_or_404(Case, pk=pk)
    if not (hasattr(request.user, "profile") and (request.user.profile.can_view_cases or request.user.profile.is_admin)):
        return HttpResponseForbidden()
    docs = case.documents.all().select_related("uploaded_by").prefetch_related("notes__created_by")
    html = render_to_string(
        "cases/_documents_content_v2.html", {"docs": docs, "object": case}, request=request
    )
    return HttpResponse(html)


@login_required
@require_http_methods(["POST"])
def case_documents_upload(request, pk):
    case = get_object_or_404(Case, pk=pk)
    if not _user_can_modify_case_documents(request.user, case):
        return HttpResponseForbidden("permission denied")
    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse({"error": "No files provided"}, status=400)
    created = []
    for f in files:
        doc = case.documents.create(
            file=f,
            name=getattr(f, "name", "") or "",
            uploaded_by=request.user,
            size=getattr(f, "size", None) or None,
            content_type=getattr(f, "content_type", "") or "",
        )
        created.append({"id": doc.pk, "name": doc.name or doc.filename()})
    return JsonResponse({"created": created}, status=201)


@login_required
@require_http_methods(["POST"])
def case_documents_delete(request, pk):
    case = get_object_or_404(Case, pk=pk)
    if not _user_can_modify_case_documents(request.user, case):
        return HttpResponseForbidden("permission denied")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        ids = payload.get("ids") or []
    except Exception:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    if not isinstance(ids, list) or not ids:
        return JsonResponse({"error": "No ids provided"}, status=400)
    deleted = []
    for doc in case.documents.filter(pk__in=ids):
        try:
            doc.file.delete(save=False)
        except Exception:
            pass
        doc.delete()
        deleted.append(doc.pk)
    return JsonResponse({"deleted": deleted})


@login_required
@require_http_methods(["GET"])
def case_document_download(request, pk, doc_pk):
    case = get_object_or_404(Case, pk=pk)
    doc = get_object_or_404(case.documents, pk=doc_pk)
    if not (hasattr(request.user, "profile") and (
        request.user.profile.can_view_cases
        or request.user.profile.is_admin
        or doc.uploaded_by == request.user
    )):
        return HttpResponseForbidden()
    try:
        fh = doc.file.open("rb")
        return FileResponse(fh, as_attachment=True, filename=doc.filename())
    except Exception:
        return HttpResponse(status=404)


@login_required
@require_http_methods(["POST"])
def case_document_add_note(request, pk, doc_pk):
    case = get_object_or_404(Case, pk=pk)
    if not (hasattr(request.user, "profile") and (request.user.profile.can_view_cases or request.user.profile.is_admin)):
        return HttpResponseForbidden("permission denied")
    doc = get_object_or_404(case.documents, pk=doc_pk)
    content = (request.POST.get("content") or "").strip()
    if not content:
        return JsonResponse({"error": "Content required"}, status=400)
    note = doc.notes.create(content=content, created_by=request.user)
    return JsonResponse({
        "created": True,
        "note": {
            "id": note.pk,
            "content": note.content,
            "created_by": note.created_by.get_full_name() or note.created_by.username,
            "created_at": note.created_at.strftime("%Y-%m-%d %H:%M"),
        },
    })


@login_required
@require_http_methods(["POST"])
def case_document_delete_note(request, pk, doc_pk, note_pk):
    case = get_object_or_404(Case, pk=pk)
    if not (hasattr(request.user, "profile") and request.user.profile.is_admin):
        return HttpResponseForbidden("permission denied")
    doc = get_object_or_404(case.documents, pk=doc_pk)
    note = get_object_or_404(doc.notes, pk=note_pk)
    note.delete()
    return JsonResponse({"deleted": True})
