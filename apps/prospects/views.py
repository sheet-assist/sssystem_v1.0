import calendar
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Min, Max, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView
from django_filters.views import FilterView
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
import json

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
        type_stats = {
            row["prospect_type"]: row
            for row in Prospect.objects.values("prospect_type").annotate(
                total_count=Count("id"),
                qualified_count=Count("id", filter=Q(qualification_status="qualified")),
                first_auction=Min("auction_date"),
                last_auction=Max("auction_date"),
                total_surplus=Sum("surplus_amount"),
            )
        }
        ctx["type_cards"] = [
            {
                "code": code,
                "label": label,
                "total_count": type_stats.get(code, {}).get("total_count", 0),
                "qualified_count": type_stats.get(code, {}).get("qualified_count", 0),
                "first_auction": type_stats.get(code, {}).get("first_auction"),
                "last_auction": type_stats.get(code, {}).get("last_auction"),
                "total_surplus": type_stats.get(code, {}).get("total_surplus") or 0,
            }
            for code, label in Prospect.PROSPECT_TYPES
        ]
        type_codes = {code for code, _label in Prospect.PROSPECT_TYPES}
        selected_type = (self.request.GET.get("prospect_type") or "").upper()
        if selected_type not in type_codes:
            selected_type = ""

        prospect_qs = Prospect.objects.select_related("county", "county__state", "assigned_to")
        if selected_type:
            prospect_qs = prospect_qs.filter(prospect_type=selected_type)

        filter_data = self.request.GET.copy()
        if not filter_data.get("qualification_status"):
            filter_data["qualification_status"] = "qualified"

        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_prospects = prospect_filter.qs.order_by("-auction_date", "-created_at")
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0

        ctx["selected_prospect_type"] = selected_type
        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        return ctx


class StateSelectView(ProspectsAccessMixin, ListView):
    template_name = "prospects/state_select.html"
    context_object_name = "states"

    def get_queryset(self):
        qs = State.objects.filter(is_active=True, counties__is_active=True).annotate(
            total_count=Count(
                "counties__prospects",
                filter=Q(counties__prospects__prospect_type=self.kwargs["prospect_type"]),
                distinct=True,
            ),
            qualified_count=Count(
                "counties__prospects",
                filter=Q(
                    counties__prospects__prospect_type=self.kwargs["prospect_type"],
                    counties__prospects__qualification_status="qualified",
                ),
                distinct=True,
            ),
            first_auction=Min(
                "counties__prospects__auction_date",
                filter=Q(counties__prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
            last_auction=Max(
                "counties__prospects__auction_date",
                filter=Q(counties__prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
            total_surplus=Sum(
                "counties__prospects__surplus_amount",
                filter=Q(counties__prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
        )
        qs = qs.filter(total_count__gt=0)
        return qs.order_by("-qualified_count", "-total_count", "name").distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs["prospect_type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["prospect_type"], "")

        prospect_qs = Prospect.objects.filter(
            prospect_type=self.kwargs["prospect_type"]
        ).select_related("county", "county__state", "assigned_to")

        filter_data = self.request.GET.copy()
        if not filter_data.get("qualification_status"):
            filter_data["qualification_status"] = "qualified"

        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_prospects = prospect_filter.qs.order_by("-auction_date", "-created_at")
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0

        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        return ctx


class CountySelectView(ProspectsAccessMixin, ListView):
    template_name = "prospects/county_select.html"
    context_object_name = "counties"

    def get_queryset(self):
        qs = County.objects.filter(
            state__abbreviation__iexact=self.kwargs["state"],
            is_active=True,
        ).select_related("state").annotate(
            total_count=Count("prospects", filter=Q(prospects__prospect_type=self.kwargs["prospect_type"])),
            qualified_count=Count(
                "prospects",
                filter=Q(
                    prospects__prospect_type=self.kwargs["prospect_type"],
                    prospects__qualification_status="qualified",
                ),
            ),
            first_auction=Min(
                "prospects__auction_date",
                filter=Q(prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
            last_auction=Max(
                "prospects__auction_date",
                filter=Q(prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
            total_surplus=Sum(
                "prospects__surplus_amount",
                filter=Q(prospects__prospect_type=self.kwargs["prospect_type"]),
            ),
        )
        qs = qs.filter(total_count__gt=0)
        return qs.order_by("-qualified_count", "-total_count", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs["prospect_type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["prospect_type"], "")
        state_abbr = self.kwargs["state"].upper()
        ctx["state_abbr"] = state_abbr

        selected_state = State.objects.filter(abbreviation__iexact=self.kwargs["state"]).first()

        prospect_qs = Prospect.objects.filter(
            prospect_type=self.kwargs["prospect_type"],
            county__state__abbreviation__iexact=self.kwargs["state"],
        ).select_related("county", "county__state", "assigned_to")

        filter_data = self.request.GET.copy()
        if not filter_data.get("qualification_status"):
            filter_data["qualification_status"] = "qualified"
        if selected_state and not filter_data.get("state"):
            filter_data["state"] = str(selected_state.pk)

        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_prospects = prospect_filter.qs.order_by("-auction_date", "-created_at")
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0

        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        return ctx


class ProspectListView(ProspectsAccessMixin, FilterView):
    model = Prospect
    template_name = "prospects/list.html"
    filterset_class = ProspectFilter
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("county", "county__state", "assigned_to")
        ptype = self.kwargs.get("prospect_type")
        state = self.kwargs.get("state") or self.request.GET.get("state")
        county_slug = self.kwargs.get("county") or self.request.GET.get("county")
        if ptype:
            qs = qs.filter(prospect_type=ptype)
        if state:
            qs = qs.filter(county__state__abbreviation__iexact=state)
        if county_slug:
            qs = qs.filter(county__slug=county_slug)
        return qs

    def get_filterset_kwargs(self, filterset_class):
        """Inject a default qualification_status=qualified when no qualification filter is provided.

        Only apply this default for the main `ProspectListView` (not for subclasses
        like QualifiedListView/DisqualifiedListView which explicitly narrow the
        queryset).
        """
        kwargs = super().get_filterset_kwargs(filterset_class)
        # Only apply default for the base class (avoid interfering with subclasses)
        if self.__class__ is ProspectListView:
            data = kwargs.get("data") or self.request.GET or {}
            has_q = False
            try:
                # QueryDict supports get
                has_q = bool(data.get("qualification_status"))
            except Exception:
                has_q = "qualification_status" in dict(data)

            if not has_q:
                # make mutable copy
                try:
                    data = data.copy()
                except Exception:
                    data = dict(data)
                data["qualification_status"] = "qualified"
                kwargs["data"] = data
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["prospect_type"] = self.kwargs.get("prospect_type", "")
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs.get("prospect_type", ""), "")
        ctx["state_abbr"] = self.kwargs.get("state", "")
        ctx["county_slug"] = self.kwargs.get("county", "")
        if self.kwargs.get("county"):
            ctx["county_obj"] = County.objects.filter(slug=self.kwargs["county"]).first()

        # --- aggregate stats for the current filtered queryset ---
        # Use the filtered queryset from the active FilterSet (available as `filter` in context)
        filtered_qs = None
        if "filter" in ctx and getattr(ctx["filter"], "qs", None) is not None:
            filtered_qs = ctx["filter"].qs
        else:
            # fallback to the view queryset (may be unfiltered by GET params)
            filtered_qs = self.get_queryset()

        from django.db.models import Sum, Min, Max

        ctx["stats_total"] = filtered_qs.count()
        ctx["stats_qualified"] = filtered_qs.filter(qualification_status="qualified").count()
        ctx["stats_surplus_sum"] = filtered_qs.aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0

        # first / last auction dates (based on active filters)
        agg_dates = filtered_qs.aggregate(first_auction=Min("auction_date"), last_auction=Max("auction_date"))
        ctx["stats_first_auction"] = agg_dates.get("first_auction")
        ctx["stats_last_auction"] = agg_dates.get("last_auction")

        return ctx


class ProspectDetailView(ProspectsAccessMixin, DetailView):
    model = Prospect
    template_name = "prospects/detail.html"

    def get_queryset(self):
        return Prospect.objects.select_related(
            "county", "county__state", "assigned_to", "assigned_by"
        ).prefetch_related(
            "notes__author",
            "action_logs__user",
            "rule_notes__created_by",
        )


# -------------------- Digital Folder endpoints --------------------

def _user_can_modify_documents(user, prospect):
    if not hasattr(user, 'profile'):
        return False
    return user.profile.is_admin or (prospect.assigned_to and prospect.assigned_to == user)


@login_required
@require_http_methods(["GET"])
def prospect_documents_list_v2(request, pk):
    prospect = get_object_or_404(Prospect, pk=pk)
    if not request.user.profile.can_view_prospects and not request.user.profile.is_admin:
        return HttpResponseForbidden()
    docs = prospect.documents.all().select_related('uploaded_by').prefetch_related('notes__created_by')
    html = render_to_string('prospects/_documents_content_v2.html', {'docs': docs, 'object': prospect}, request=request)
    return HttpResponse(html)


class ProspectDocumentsPageV2View(ProspectsAccessMixin, DetailView):
    """Dedicated Digital Folder V2 page (opens in new tab)."""
    model = Prospect
    template_name = 'prospects/documents_page_v2.html'

    def get_queryset(self):
        return Prospect.objects.select_related('county', 'county__state').prefetch_related('documents__uploaded_by', 'documents__notes__created_by')


@login_required
@require_http_methods(["POST"])
def prospect_document_add_note(request, pk, doc_pk):
    """Add a note to a ProspectDocument (AJAX POST).

    Body form fields: content
    Returns: JSON { created: true, note_id: <id> }
    """
    prospect = get_object_or_404(Prospect, pk=pk)
    if not request.user.profile.can_view_prospects and not request.user.profile.is_admin:
        return HttpResponseForbidden('permission denied')

    doc = get_object_or_404(prospect.documents, pk=doc_pk)
    content = (request.POST.get('content') or '').strip()
    if not content:
        return JsonResponse({'error': 'Content required'}, status=400)

    note = doc.notes.create(content=content, created_by=request.user)
    return JsonResponse({
        'created': True,
        'note': {
            'id': note.pk,
            'content': note.content,
            'created_by': note.created_by.get_full_name() or note.created_by.username,
            'created_at': note.created_at.strftime('%Y-%m-%d %H:%M'),
        }
    })


@login_required
@require_http_methods(["POST"])
def prospect_document_delete_note(request, pk, doc_pk, note_pk):
    """Delete a ProspectDocumentNote (admin only). Returns JSON { deleted: True }."""
    prospect = get_object_or_404(Prospect, pk=pk)
    if not request.user.profile.is_admin:
        return HttpResponseForbidden('permission denied')
    doc = get_object_or_404(prospect.documents, pk=doc_pk)
    note = get_object_or_404(doc.notes, pk=note_pk)
    note.delete()
    return JsonResponse({'deleted': True})


@login_required
@require_http_methods(["POST"])
def prospect_documents_upload(request, pk):
    prospect = get_object_or_404(Prospect, pk=pk)
    if not _user_can_modify_documents(request.user, prospect):
        return HttpResponseForbidden('permission denied')

    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({'error': 'No files provided'}, status=400)

    created = []
    for f in files:
        doc = prospect.documents.create(
            file=f,
            name=getattr(f, 'name', '') or '',
            uploaded_by=request.user,
            size=getattr(f, 'size', None) or None,
            content_type=getattr(f, 'content_type', '') or '',
        )
        created.append({'id': doc.pk, 'name': doc.name or doc.filename()})

    return JsonResponse({'created': created}, status=201)


@login_required
@require_http_methods(["POST"])
def prospect_documents_delete(request, pk):
    prospect = get_object_or_404(Prospect, pk=pk)
    if not _user_can_modify_documents(request.user, prospect):
        return HttpResponseForbidden('permission denied')

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        ids = payload.get('ids') or []
    except Exception:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    if not isinstance(ids, list) or not ids:
        return JsonResponse({'error': 'No ids provided'}, status=400)

    deleted = []
    for doc in prospect.documents.filter(pk__in=ids):
        # delete file from storage
        try:
            doc.file.delete(save=False)
        except Exception:
            pass
        doc.delete()
        deleted.append(doc.pk)

    return JsonResponse({'deleted': deleted})


@login_required
@require_http_methods(["GET"])
def prospect_document_download(request, pk, doc_pk):
    prospect = get_object_or_404(Prospect, pk=pk)
    doc = get_object_or_404(prospect.documents, pk=doc_pk)
    if not (request.user.profile.can_view_prospects or request.user.profile.is_admin or doc.uploaded_by == request.user):
        return HttpResponseForbidden()
    # Stream file response
    try:
        fh = doc.file.open('rb')
        return FileResponse(fh, as_attachment=True, filename=doc.filename())
    except Exception:
        return HttpResponse(status=404)

# ------------------------------------------------------------------


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


class ProspectDeleteView(AdminRequiredMixin, DeleteView):
    model = Prospect
    http_method_names = ["post"]

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        case_number = self.object.case_number
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Prospect {case_number} deleted successfully.")
        return response

    def get_success_url(self):
        next_url = self.request.POST.get("next")
        if next_url:
            return next_url
        return reverse("prospects:list_by_type", kwargs={"prospect_type": self.object.prospect_type})


TYPE_BADGE_MAP = {
    "MF": "bg-primary",
    "TD": "bg-warning text-dark",
    "TL": "bg-info text-dark",
    "SS": "bg-danger",
}


class ProspectCaseCalendarView(ProspectsAccessMixin, TemplateView):
    template_name = "prospects/calendar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        year, month = self._resolve_year_month(today)
        selected_type = self.request.GET.get("type", "").upper()
        selected_state = self.request.GET.get("state", "").upper()
        selected_county = self.request.GET.get("county", "")

        state_choices = State.objects.filter(is_active=True).order_by("name")
        if selected_state and not state_choices.filter(abbreviation__iexact=selected_state).exists():
            selected_state = ""

        county_choices = County.objects.none()
        if selected_state:
            county_choices = County.objects.filter(
                is_active=True, state__abbreviation__iexact=selected_state
            ).order_by("name")
            if selected_county and not county_choices.filter(slug=selected_county).exists():
                selected_county = ""
        else:
            selected_county = ""

        first_day = date(year, month, 1)
        next_month = (first_day + timedelta(days=32)).replace(day=1)

        counts_by_day, total_events, month_qualified_total = self._build_prospect_day_counts(
            first_day, next_month, selected_type, selected_state, selected_county
        )
        weeks = self._build_calendar_weeks(
            year, month, counts_by_day, selected_type, selected_state, selected_county
        )

        prev_month = (first_day - timedelta(days=1)).replace(day=1)
        next_month_display = next_month

        base_params = {}
        if selected_type:
            base_params["type"] = selected_type
        if selected_state:
            base_params["state"] = selected_state
        if selected_county:
            base_params["county"] = selected_county

        ctx.update(
            {
                "current_month": first_day,
                "weeks": weeks,
                "selected_type": selected_type,
                "selected_state": selected_state,
                "selected_county": selected_county,
                "type_choices": Prospect.PROSPECT_TYPES,
                "state_choices": state_choices,
                "county_choices": county_choices,
                "prev_query": urlencode({**base_params, "year": prev_month.year, "month": prev_month.month}),
                "next_query": urlencode({**base_params, "year": next_month_display.year, "month": next_month_display.month}),
                "today_query": urlencode({**base_params, "year": today.year, "month": today.month}),
                "prev_month": prev_month,
                "next_month": next_month_display,
                "total_events": total_events,
                "month_qualified_total": month_qualified_total,
                "weekdays": list(calendar.day_name),
                "today": today,
            }
        )
        return ctx

    def _resolve_year_month(self, today):
        try:
            year = int(self.request.GET.get("year", today.year))
            month = int(self.request.GET.get("month", today.month))
        except (TypeError, ValueError):
            return today.year, today.month
        month = min(max(month, 1), 12)
        return year, month

    def _build_prospect_day_counts(self, start_date, next_month, selected_type, selected_state, selected_county):
        qs = Prospect.objects.filter(auction_date__gte=start_date, auction_date__lt=next_month)
        if selected_type:
            qs = qs.filter(prospect_type=selected_type)
        if selected_state:
            qs = qs.filter(county__state__abbreviation__iexact=selected_state)
        if selected_county:
            qs = qs.filter(county__slug=selected_county)

        daily = qs.values("auction_date").annotate(
            total_count=Count("id"),
            qualified_count=Count("id", filter=Q(qualification_status="qualified")),
        )

        counts = {}
        total = 0
        qualified_total = 0
        for row in daily:
            day = row["auction_date"]
            total += row["total_count"]
            qualified_total += row["qualified_count"]
            counts[day] = {
                "qualified_count": row["qualified_count"],
                "total_count": row["total_count"],
            }
        return counts, total, qualified_total

    def _build_calendar_weeks(self, year, month, counts, selected_type, selected_state, selected_county):
        if selected_type:
            base_url = reverse("prospects:list_by_type", kwargs={"prospect_type": selected_type})
        else:
            base_url = reverse("prospects:list_all")

        cal = calendar.Calendar()
        weeks = []
        current_week = []
        for day in cal.itermonthdates(year, month):
            count_data = counts.get(day, {})
            base_query = {
                "auction_date_from": day.isoformat(),
                "auction_date_to": day.isoformat(),
            }
            if selected_state:
                base_query["state"] = selected_state
            if selected_county:
                base_query["county"] = selected_county
            total_url = f"{base_url}?{urlencode(base_query)}"
            qualified_url = f"{base_url}?{urlencode({**base_query, 'qualification_status': 'qualified'})}"
            current_week.append(
                {
                    "date": day,
                    "in_month": day.month == month,
                    "qualified_count": count_data.get("qualified_count", 0),
                    "total_count": count_data.get("total_count", 0),
                    "qualified_url": qualified_url,
                    "total_url": total_url,
                }
            )
            if len(current_week) == 7:
                weeks.append(current_week)
                current_week = []
        return weeks
