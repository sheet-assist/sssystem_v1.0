import calendar
from datetime import date, timedelta
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Min, Max, Sum, F, Value, ExpressionWrapper, DecimalField, Case, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView
from django_filters.views import FilterView
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
import json

from apps.accounts.mixins import AdminRequiredMixin, ProspectsAccessMixin
from apps.locations.models import County, State
from apps.settings_app.models import SSRevenueSetting

from .filters import ProspectFilter
from .forms import AssignProspectForm, ProspectNoteForm, ResearchForm, WorkflowTransitionForm
from .models import Prospect, ProspectNote, ProspectTDMDocument, log_prospect_action
from django.views.generic import FormView
from django.shortcuts import render

User = get_user_model()


# --- Phase 5: Navigation Flow ---

def _xls_cell(value):
    text = "" if value is None else str(value)
    return f'<Cell><Data ss:Type="String">{escape(text)}</Data></Cell>'


def export_prospects_excel_response(queryset, filename_prefix="prospects"):
    headers = [
        "Case #",
        "Type",
        "State",
        "County",
        "Parcel ID",
        "Address",
        "City",
        "Zip",
        "Auction Date",
        "Surplus",
        "Qualification",
        "Status",
        "AC URL",
        "TDM URL",
        "Assigned To",
    ]

    rows = []
    for p in queryset.select_related("county", "county__state", "assigned_to"):
        assigned_to = ""
        if p.assigned_to:
            assigned_to = p.assigned_to.get_full_name() or p.assigned_to.username
        rows.append(
            [
                p.case_number,
                p.get_prospect_type_display(),
                p.county.state.abbreviation if p.county_id and p.county.state_id else "",
                p.county.name if p.county_id else "",
                p.parcel_id or "",
                p.property_address or "",
                p.city or "",
                p.zip_code or "",
                p.auction_date.isoformat() if p.auction_date else "",
                f"{p.surplus_amount:.2f}" if p.surplus_amount is not None else "",
                p.get_qualification_status_display(),
                p.get_workflow_status_display(),
                p.ack_url or "",
                p.tdm_url or "",
                assigned_to,
            ]
        )

    header_xml = "<Row>" + "".join(_xls_cell(h) for h in headers) + "</Row>"
    rows_xml = "".join("<Row>" + "".join(_xls_cell(v) for v in row) + "</Row>" for row in rows)

    xml = (
        '<?xml version="1.0"?>'
        '<?mso-application progid="Excel.Sheet"?>'
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:html="http://www.w3.org/TR/REC-html40">'
        '<Worksheet ss:Name="Prospects"><Table>'
        f"{header_xml}{rows_xml}"
        "</Table></Worksheet></Workbook>"
    )

    response = HttpResponse(xml, content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{filename_prefix}_{timezone.localdate().isoformat()}.xls"'
    return response


class ProspectExcelExportMixin:
    export_param = "export"
    export_value = "excel"
    export_filename_prefix = "prospects"

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get(self.export_param) == self.export_value:
            filter_obj = context.get("filter")
            if filter_obj is not None and getattr(filter_obj, "qs", None) is not None:
                qs = filter_obj.qs
            else:
                qs = context.get("object_list", Prospect.objects.none())
            return export_prospects_excel_response(qs, self.export_filename_prefix)
        return super().render_to_response(context, **response_kwargs)


def _can_view_revenue(user):
    return hasattr(user, "profile") and (user.profile.is_admin or user.profile.can_manage_finance_settings)


def _get_ss_revenue_tier():
    return SSRevenueSetting.get_solo().tier_percent


def _annotate_revenue(qs, tier_percent):
    return qs.annotate(
        ss_revenue_amount=ExpressionWrapper(
            (F("surplus_amount") * Value(tier_percent)) / Value(100),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


def _annotate_ars_calculations(qs):
    """Annotate ARS tier, ARS amount, and SS benefit for each prospect."""
    from django.db import models as db_models
    
    # Get global ARS tier as fallback
    global_ars_tier = SSRevenueSetting.get_solo().ars_tier_percent
    
    return qs.annotate(
        ars_tier_percent=Case(
            When(assigned_to__isnull=False, then=F("assigned_to__profile__ars_tier_percent")),
            default=Value(global_ars_tier),
            output_field=db_models.IntegerField(),
        ),
        ars_amount=ExpressionWrapper(
            (F("ss_revenue_amount") * F("ars_tier_percent")) / Value(100),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        ss_benefit=ExpressionWrapper(
            F("ss_revenue_amount") - F("ars_amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


PROSPECT_TABLE_ALLOWED_SORTS = {
    "case_number",
    "auction_date",
    "surplus_amount",
    "qualification_status",
    "workflow_status",
    "assigned_to",
}


def _get_prospect_table_sort(request, allowed_sorts=None, default_sort="auction_date"):
    allowed = allowed_sorts or PROSPECT_TABLE_ALLOWED_SORTS
    sort = (request.GET.get("sort") or default_sort).strip()
    if sort not in allowed:
        sort = default_sort
    direction = (request.GET.get("dir") or "asc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    return sort, direction


def _get_prospect_table_ordering(sort, direction):
    is_desc = direction == "desc"
    tie_breaker = "-created_at" if is_desc else "created_at"

    if sort == "auction_date":
        primary = F("auction_date").desc(nulls_last=True) if is_desc else F("auction_date").asc(nulls_last=True)
        return [primary, tie_breaker]
    if sort == "surplus_amount":
        primary = F("surplus_amount").desc(nulls_last=True) if is_desc else F("surplus_amount").asc(nulls_last=True)
        return [primary, tie_breaker]
    if sort == "case_number":
        return ["-case_number" if is_desc else "case_number", tie_breaker]
    if sort == "qualification_status":
        return ["-qualification_status" if is_desc else "qualification_status", tie_breaker]
    if sort == "workflow_status":
        return ["-workflow_status" if is_desc else "workflow_status", tie_breaker]
    if sort == "assigned_to":
        primary = F("assigned_to__username").desc(nulls_last=True) if is_desc else F("assigned_to__username").asc(nulls_last=True)
        return [primary, tie_breaker]
    return [F("auction_date").asc(nulls_last=True), "created_at"]


def _build_prospect_sort_context(request, sort, direction, columns):
    sort_urls = {}
    active_dirs = {}
    for col in columns:
        qd = request.GET.copy()
        next_dir = "desc" if (sort == col and direction == "asc") else "asc"
        qd["sort"] = col
        qd["dir"] = next_dir
        qd.pop("page", None)
        sort_urls[col] = f"?{qd.urlencode()}"
        active_dirs[col] = direction if sort == col else ""
    return sort_urls, active_dirs

class TypeSelectView(ProspectsAccessMixin, ProspectExcelExportMixin, TemplateView):
    template_name = "prospects/type_select.html"
    export_filename_prefix = "prospects_type"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        can_view_revenue = _can_view_revenue(self.request.user)
        ss_revenue_tier = _get_ss_revenue_tier()
        ctx["types"] = Prospect.PROSPECT_TYPES
        type_stats = {
            row["prospect_type"]: row
            for row in Prospect.objects.values("prospect_type").annotate(
                total_count=Count("id"),
                qualified_count=Count("id", filter=Q(qualification_status="qualified")),
                first_auction=Min("auction_date"),
                last_auction=Max("auction_date"),
                total_surplus=Sum("surplus_amount", filter=Q(qualification_status="qualified")),
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
                "total_revenue": ((type_stats.get(code, {}).get("total_surplus") or 0) * ss_revenue_tier / 100),
            }
            for code, label in Prospect.PROSPECT_TYPES
            if type_stats.get(code, {}).get("total_count", 0) > 0
        ]
        type_codes = {code for code, _label in Prospect.PROSPECT_TYPES}
        selected_type = (self.request.GET.get("prospect_type") or "").upper()
        if selected_type not in type_codes:
            selected_type = ""

        prospect_qs = Prospect.objects.select_related("county", "county__state", "assigned_to", "assigned_to__profile")
        if selected_type:
            prospect_qs = prospect_qs.filter(prospect_type=selected_type)

        filter_data = self.request.GET.copy()
        if "qualification_status" not in filter_data:
            filter_data["qualification_status"] = "qualified"
        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_qs = prospect_filter.qs
        if can_view_revenue:
            filtered_qs = _annotate_revenue(filtered_qs, ss_revenue_tier)
            filtered_qs = _annotate_ars_calculations(filtered_qs)
        sort_columns = ["case_number", "auction_date", "surplus_amount", "qualification_status", "workflow_status", "assigned_to"]
        sort, direction = _get_prospect_table_sort(self.request, allowed_sorts=set(sort_columns))
        filtered_prospects = filtered_qs.order_by(*_get_prospect_table_ordering(sort, direction))
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.filter(qualification_status="qualified").aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0
        sort_urls, active_dirs = _build_prospect_sort_context(self.request, sort, direction, sort_columns)

        ctx["selected_prospect_type"] = selected_type
        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        ctx["filtered_revenue"] = (filtered_surplus * ss_revenue_tier / 100) if can_view_revenue else 0
        ctx["can_view_revenue"] = can_view_revenue
        ctx["ss_revenue_tier"] = ss_revenue_tier
        ctx["current_sort"] = sort
        ctx["current_sort_dir"] = direction
        ctx["sort_urls"] = sort_urls
        ctx["active_sort_dirs"] = active_dirs
        return ctx


class ProspectAutodialerView(ProspectsAccessMixin, DetailView):
    model = Prospect
    template_name = "prospects/autodialer.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # minimal context for now; integration with an autodialer service can be added later
        ctx["phone_numbers"] = []
        return ctx


class ProspectEmailView(ProspectsAccessMixin, DetailView):
    model = Prospect
    template_name = "prospects/email_send.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["email_addresses"] = []
        return ctx
    


class StateSelectView(ProspectsAccessMixin, ProspectExcelExportMixin, ListView):
    template_name = "prospects/state_select.html"
    context_object_name = "states"
    export_filename_prefix = "prospects_state"

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
                filter=Q(
                    counties__prospects__prospect_type=self.kwargs["prospect_type"],
                    counties__prospects__qualification_status="qualified",
                ),
            ),
        )
        qs = qs.filter(total_count__gt=0)
        return qs.order_by("-qualified_count", "-total_count", "name").distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        can_view_revenue = _can_view_revenue(self.request.user)
        ss_revenue_tier = _get_ss_revenue_tier()
        ctx["prospect_type"] = self.kwargs["prospect_type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["prospect_type"], "")
        if can_view_revenue:
            for state_obj in ctx["states"]:
                state_obj.total_revenue = ((state_obj.total_surplus or 0) * ss_revenue_tier / 100)

        prospect_qs = Prospect.objects.filter(
            prospect_type=self.kwargs["prospect_type"]
        ).select_related("county", "county__state", "assigned_to")

        filter_data = self.request.GET.copy()
        if "qualification_status" not in filter_data:
            filter_data["qualification_status"] = "qualified"

        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_qs = prospect_filter.qs
        if can_view_revenue:
            filtered_qs = _annotate_revenue(filtered_qs, ss_revenue_tier)
            filtered_qs = _annotate_ars_calculations(filtered_qs)
        sort_columns = ["case_number", "auction_date", "surplus_amount", "qualification_status", "workflow_status"]
        sort, direction = _get_prospect_table_sort(self.request, allowed_sorts=set(sort_columns))
        filtered_prospects = filtered_qs.order_by(*_get_prospect_table_ordering(sort, direction))
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.filter(qualification_status="qualified").aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0
        sort_urls, active_dirs = _build_prospect_sort_context(self.request, sort, direction, sort_columns)

        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        ctx["filtered_revenue"] = (filtered_surplus * ss_revenue_tier / 100) if can_view_revenue else 0
        ctx["can_view_revenue"] = can_view_revenue
        ctx["ss_revenue_tier"] = ss_revenue_tier
        ctx["current_sort"] = sort
        ctx["current_sort_dir"] = direction
        ctx["sort_urls"] = sort_urls
        ctx["active_sort_dirs"] = active_dirs
        return ctx


class CountySelectView(ProspectsAccessMixin, ProspectExcelExportMixin, ListView):
    template_name = "prospects/county_select.html"
    context_object_name = "counties"
    export_filename_prefix = "prospects_county"

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
        can_view_revenue = _can_view_revenue(self.request.user)
        ss_revenue_tier = _get_ss_revenue_tier()
        ctx["prospect_type"] = self.kwargs["prospect_type"]
        ctx["type_display"] = dict(Prospect.PROSPECT_TYPES).get(self.kwargs["prospect_type"], "")
        state_abbr = self.kwargs["state"].upper()
        ctx["state_abbr"] = state_abbr
        if can_view_revenue:
            for county_obj in ctx["counties"]:
                county_obj.total_revenue = ((county_obj.total_surplus or 0) * ss_revenue_tier / 100)

        selected_state = State.objects.filter(abbreviation__iexact=self.kwargs["state"]).first()

        prospect_qs = Prospect.objects.filter(
            prospect_type=self.kwargs["prospect_type"],
            county__state__abbreviation__iexact=self.kwargs["state"],
        ).select_related("county", "county__state", "assigned_to")

        filter_data = self.request.GET.copy()
        if "qualification_status" not in filter_data:
            filter_data["qualification_status"] = "qualified"
        if selected_state and not filter_data.get("state"):
            filter_data["state"] = str(selected_state.pk)

        prospect_filter = ProspectFilter(filter_data, queryset=prospect_qs)
        filtered_qs = prospect_filter.qs
        if can_view_revenue:
            filtered_qs = _annotate_revenue(filtered_qs, ss_revenue_tier)
            filtered_qs = _annotate_ars_calculations(filtered_qs)
        sort_columns = ["case_number", "auction_date", "surplus_amount", "qualification_status", "workflow_status"]
        sort, direction = _get_prospect_table_sort(self.request, allowed_sorts=set(sort_columns))
        filtered_prospects = filtered_qs.order_by(*_get_prospect_table_ordering(sort, direction))
        paginator = Paginator(filtered_prospects, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        has_active_filters = any(k != "page" and bool(v) for k, v in self.request.GET.items())
        filtered_surplus = prospect_filter.qs.filter(qualification_status="qualified").aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0
        sort_urls, active_dirs = _build_prospect_sort_context(self.request, sort, direction, sort_columns)

        ctx["filter"] = prospect_filter
        ctx["prospect_list"] = page_obj.object_list
        ctx["page_obj"] = page_obj
        ctx["paginator"] = paginator
        ctx["is_paginated"] = page_obj.has_other_pages()
        ctx["has_active_filters"] = has_active_filters
        ctx["filtered_total"] = prospect_filter.qs.count()
        ctx["filtered_surplus"] = filtered_surplus
        ctx["filtered_revenue"] = (filtered_surplus * ss_revenue_tier / 100) if can_view_revenue else 0
        ctx["can_view_revenue"] = can_view_revenue
        ctx["ss_revenue_tier"] = ss_revenue_tier
        ctx["current_sort"] = sort
        ctx["current_sort_dir"] = direction
        ctx["sort_urls"] = sort_urls
        ctx["active_sort_dirs"] = active_dirs
        return ctx


class ProspectListView(ProspectsAccessMixin, ProspectExcelExportMixin, FilterView):
    model = Prospect
    template_name = "prospects/list.html"
    filterset_class = ProspectFilter
    paginate_by = 25
    export_filename_prefix = "prospects_list"
    ALLOWED_SORTS = {
        "case_number",
        "auction_date",
        "surplus_amount",
        "qualification_status",
        "workflow_status",
        "assigned_to",
    }

    def _get_sort(self):
        sort = (self.request.GET.get("sort") or "auction_date").strip()
        if sort not in self.ALLOWED_SORTS:
            sort = "auction_date"
        direction = (self.request.GET.get("dir") or "asc").strip().lower()
        if direction not in {"asc", "desc"}:
            direction = "asc"
        return sort, direction

    def _get_ordering(self, sort, direction):
        is_desc = direction == "desc"
        tie_breaker = "-created_at" if is_desc else "created_at"

        if sort == "auction_date":
            primary = F("auction_date").desc(nulls_last=True) if is_desc else F("auction_date").asc(nulls_last=True)
            return [primary, tie_breaker]
        if sort == "surplus_amount":
            primary = F("surplus_amount").desc(nulls_last=True) if is_desc else F("surplus_amount").asc(nulls_last=True)
            return [primary, tie_breaker]
        if sort == "case_number":
            return ["-case_number" if is_desc else "case_number", tie_breaker]
        if sort == "qualification_status":
            return ["-qualification_status" if is_desc else "qualification_status", tie_breaker]
        if sort == "workflow_status":
            return ["-workflow_status" if is_desc else "workflow_status", tie_breaker]
        if sort == "assigned_to":
            primary = F("assigned_to__username").desc(nulls_last=True) if is_desc else F("assigned_to__username").asc(nulls_last=True)
            return [primary, tie_breaker]
        return [F("auction_date").asc(nulls_last=True), "created_at"]

    def _build_sort_context(self, sort, direction):
        columns = ["case_number", "auction_date", "surplus_amount", "qualification_status", "workflow_status", "assigned_to"]
        sort_urls = {}
        active_dirs = {}
        for col in columns:
            qd = self.request.GET.copy()
            next_dir = "desc" if (sort == col and direction == "asc") else "asc"
            qd["sort"] = col
            qd["dir"] = next_dir
            qd.pop("page", None)
            sort_urls[col] = f"?{qd.urlencode()}"
            active_dirs[col] = direction if sort == col else ""
        return sort_urls, active_dirs

    def get_queryset(self):
        qs = super().get_queryset().select_related("county", "county__state", "assigned_to")
        if _can_view_revenue(self.request.user):
            qs = _annotate_revenue(qs, _get_ss_revenue_tier())
        ptype = self.kwargs.get("prospect_type")
        state = self.kwargs.get("state") or self.request.GET.get("state")
        county_slug = self.kwargs.get("county") or self.request.GET.get("county")
        if ptype:
            qs = qs.filter(prospect_type=ptype)
        if state:
            qs = qs.filter(county__state__abbreviation__iexact=state)
        if county_slug:
            qs = qs.filter(county__slug=county_slug)
        sort, direction = self._get_sort()
        return qs.order_by(*self._get_ordering(sort, direction))

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
        ctx["can_view_revenue"] = _can_view_revenue(self.request.user)
        ctx["ss_revenue_tier"] = _get_ss_revenue_tier()
        if self.kwargs.get("county"):
            ctx["county_obj"] = County.objects.filter(slug=self.kwargs["county"]).first()
        sort, direction = self._get_sort()
        sort_urls, active_dirs = self._build_sort_context(sort, direction)
        ctx["current_sort"] = sort
        ctx["current_sort_dir"] = direction
        ctx["sort_urls"] = sort_urls
        ctx["active_sort_dirs"] = active_dirs

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
        ctx["stats_surplus_sum"] = filtered_qs.filter(qualification_status="qualified").aggregate(total_surplus=Sum("surplus_amount"))["total_surplus"] or 0

        # first / last auction dates (based on active filters)
        agg_dates = filtered_qs.aggregate(first_auction=Min("auction_date"), last_auction=Max("auction_date"))
        ctx["stats_first_auction"] = agg_dates.get("first_auction")
        ctx["stats_last_auction"] = agg_dates.get("last_auction")

        return ctx


_PROSPECT_ACTION_MAP = {
    "qualified":         ("Qualified",           "success",   "bi-check-circle-fill"),
    "disqualified":      ("Disqualified",        "danger",    "bi-x-circle-fill"),
    "assigned":          ("Assigned",            "info",      "bi-person-check-fill"),
    "status_changed":    ("Workflow Changed",    "secondary", "bi-arrow-right-circle-fill"),
    "converted_to_case": ("Converted to Case",  "purple",    "bi-arrow-up-circle-fill"),
    "email_sent":        ("Email Sent",          "warning",   "bi-envelope-fill"),
}

_CASE_ACTION_MAP = {
    "closed_won":  ("Case Closed Won",  "success", "bi-trophy-fill"),
    "closed_lost": ("Case Closed Lost", "danger",  "bi-x-octagon-fill"),
}


def _build_lifecycle_timeline(prospect):
    if prospect is None:
        return []

    events = []

    # Prospect created
    events.append({
        "date": prospect.created_at,
        "phase": "prospect",
        "event_type": "prospect_created",
        "label": "Prospect Created",
        "description": str(prospect),
        "actor": "System",
        "icon": "bi-plus-circle-fill",
        "color": "primary",
    })

    # Prospect action logs
    for log in prospect.action_logs.filter(
        action_type__in=_PROSPECT_ACTION_MAP
    ).order_by("created_at").select_related("user"):
        label, color, icon = _PROSPECT_ACTION_MAP[log.action_type]
        events.append({
            "date": log.created_at,
            "phase": "prospect",
            "event_type": log.action_type,
            "label": label,
            "description": log.description,
            "actor": str(log.user) if log.user else "System",
            "icon": icon,
            "color": color,
        })

    # Case phase
    if hasattr(prospect, "case") and prospect.case:
        case = prospect.case

        events.append({
            "date": case.created_at,
            "phase": "case",
            "event_type": "case_created",
            "label": "Case Created",
            "description": f"Case #{case.case_number}" if case.case_number else "",
            "actor": "System",
            "icon": "bi-folder2-open",
            "color": "success",
        })

        if case.contract_date:
            from django.utils import timezone as tz
            import datetime
            contract_dt = datetime.datetime.combine(
                case.contract_date, datetime.time.min,
                tzinfo=tz.get_current_timezone(),
            )
            events.append({
                "date": contract_dt,
                "phase": "case",
                "event_type": "contract_signed",
                "label": "Contract Signed",
                "description": "",
                "actor": "System",
                "icon": "bi-file-earmark-check-fill",
                "color": "teal",
            })

        for log in case.action_logs.order_by("created_at").select_related("user"):
            label, color, icon = _CASE_ACTION_MAP.get(
                log.action_type,
                ("Case Status Change", "secondary", "bi-arrow-right-circle-fill"),
            )
            events.append({
                "date": log.created_at,
                "phase": "case",
                "event_type": log.action_type,
                "label": label,
                "description": log.description,
                "actor": str(log.user) if log.user else "System",
                "icon": icon,
                "color": color,
            })

    events.sort(key=lambda e: e["date"])
    return events


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
            "tdm_documents",
            "case__action_logs__user",
        )

    def get_context_data(self, **kwargs):
        from django.db.models import Max
        ctx = super().get_context_data(**kwargs)
        ctx["tdm_downloaded_docs"] = self.object.tdm_documents.filter(is_downloaded=True)
        ctx["tdm_last_sync"] = self.object.tdm_documents.aggregate(Max("last_checked_at"))["last_checked_at__max"]
        ctx["timeline"] = _build_lifecycle_timeline(self.object)
        return ctx


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
        return Prospect.objects.select_related('county', 'county__state').prefetch_related(
            'documents__uploaded_by', 'documents__notes__created_by', 'tdm_documents'
        )

    def get_context_data(self, **kwargs):
        from django.db.models import Max
        ctx = super().get_context_data(**kwargs)
        ctx["tdm_last_sync"] = self.object.tdm_documents.aggregate(Max("last_checked_at"))["last_checked_at__max"]
        return ctx


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


@login_required
@require_http_methods(["GET"])
def prospect_tdm_document_open(request, pk, tdm_doc_pk):
    """Serve a downloaded TDM document inline (opens in browser tab)."""
    from pathlib import Path
    from django.conf import settings as django_settings

    prospect = get_object_or_404(Prospect, pk=pk)
    if not (request.user.profile.can_view_prospects or request.user.profile.is_admin):
        return HttpResponseForbidden()

    tdm_doc = get_object_or_404(ProspectTDMDocument, pk=tdm_doc_pk, prospect=prospect)
    if not tdm_doc.is_downloaded or not tdm_doc.local_path:
        return HttpResponse("File not downloaded yet.", status=404)

    raw_path = (tdm_doc.local_path or "").strip()
    normalized = raw_path.replace("\\", "/")
    rel_path = Path(normalized)

    media_root = Path(getattr(django_settings, "MEDIA_ROOT", "") or "").resolve() if getattr(django_settings, "MEDIA_ROOT", None) else None
    base_dir = Path(getattr(django_settings, "BASE_DIR", Path(__file__).resolve().parent.parent.parent)).resolve()

    candidates = []
    if Path(raw_path).is_absolute():
        candidates.append(Path(raw_path))
    if media_root:
        candidates.append(media_root / rel_path)
    candidates.append(base_dir / rel_path)

    # Backward-compat for old records stored as BASE_DIR-relative media paths.
    if media_root and normalized.startswith("media/"):
        candidates.append(media_root / Path(normalized[len("media/"):]))

    file_path = next((p for p in candidates if p.exists()), None)
    if not file_path:
        return HttpResponse("File not found on disk.", status=404)

    try:
        fname = file_path.name
        return FileResponse(open(file_path, "rb"), content_type="application/pdf", filename=fname)
    except Exception:
        return HttpResponse(status=500)

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

class MyProspectsView(ProspectsAccessMixin, ProspectExcelExportMixin, FilterView):
    model = Prospect
    template_name = "prospects/list.html"
    filterset_class = ProspectFilter
    paginate_by = 25
    export_filename_prefix = "prospects_my"

    def get_queryset(self):
        qs = Prospect.objects.filter(
            assigned_to=self.request.user
        ).select_related("county", "county__state", "assigned_to")
        if _can_view_revenue(self.request.user):
            qs = _annotate_revenue(qs, _get_ss_revenue_tier())
        return qs.order_by(
            F("auction_date").asc(nulls_last=True), "created_at"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "My Prospects"
        ctx["can_view_revenue"] = _can_view_revenue(self.request.user)
        ctx["ss_revenue_tier"] = _get_ss_revenue_tier()
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


# -------------------- TDM On-Demand Sync endpoints --------------------

@login_required
@require_POST
def prospect_tdm_sync(request, pk):
    """POST: start a background TDM document sync for a single prospect."""
    from apps.scraper.services.tdm_sync_service import start_tdm_sync
    prospect = get_object_or_404(Prospect, pk=pk)
    if not prospect.case_number:
        return JsonResponse({"error": "No case number on this prospect."}, status=400)
    started = start_tdm_sync(prospect.pk)
    if not started:
        return JsonResponse({"error": "Sync already running."}, status=409)
    return JsonResponse({"started": True})


@login_required
def prospect_tdm_sync_status(request, pk):
    """GET: return the current sync status for a prospect (for polling)."""
    from apps.scraper.services.tdm_sync_service import get_sync_status
    prospect = get_object_or_404(Prospect, pk=pk)
    return JsonResponse(get_sync_status(prospect.pk))


@login_required
def prospect_tdm_docs_fragment(request, pk):
    """GET: render the TDM Documents card partial for in-place DOM refresh."""
    prospect = get_object_or_404(
        Prospect.objects.prefetch_related("tdm_documents"), pk=pk
    )
    downloaded = prospect.tdm_documents.filter(is_downloaded=True)
    last_sync = prospect.tdm_documents.aggregate(Max("last_checked_at"))["last_checked_at__max"]
    return render(request, "prospects/_tdm_docs_fragment.html", {
        "object": prospect,
        "tdm_downloaded_docs": downloaded,
        "tdm_last_sync": last_sync,
    })


