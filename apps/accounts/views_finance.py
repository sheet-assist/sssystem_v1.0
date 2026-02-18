from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import UserProfile
from apps.locations.models import County, State
from apps.prospects.models import Prospect
from apps.settings_app.models import SSRevenueSetting

User = get_user_model()

TYPE_MAP = dict(Prospect.PROSPECT_TYPES)


def _build_base_qs(params):
    """Build a filtered Prospect queryset from request params dict."""
    start = params.get("start")
    end = params.get("end")
    state_id = params.get("state")
    county_id = params.get("county")
    prospect_types = params.get("prospect_types")  # list
    qualification_status = params.get("qualification_status", "qualified")

    qs = Prospect.objects.all()

    if start and end:
        qs = qs.filter(qualification_date__date__gte=start, qualification_date__date__lte=end)
    elif start:
        qs = qs.filter(qualification_date__date__gte=start)
    elif end:
        qs = qs.filter(qualification_date__date__lte=end)

    if qualification_status:
        qs = qs.filter(qualification_status=qualification_status)

    if state_id:
        qs = qs.filter(county__state_id=state_id)

    if county_id:
        qs = qs.filter(county_id=county_id)

    if prospect_types:
        qs = qs.filter(prospect_type__in=prospect_types)

    return qs


def _compute_kpi(qs, tier_percent, ars_tier_percent):
    agg = qs.aggregate(
        total_surplus=Sum("surplus_amount"),
        prospect_count=Count("id"),
    )
    total_surplus = float(agg["total_surplus"] or 0)
    prospect_count = agg["prospect_count"] or 0
    ss_revenue = total_surplus * tier_percent / 100
    ars_payout = ss_revenue * ars_tier_percent / 100
    ss_net_benefit = ss_revenue - ars_payout
    avg_surplus = total_surplus / prospect_count if prospect_count else 0
    return {
        "total_surplus": round(total_surplus, 2),
        "ss_revenue": round(ss_revenue, 2),
        "ars_payout": round(ars_payout, 2),
        "ss_net_benefit": round(ss_net_benefit, 2),
        "avg_surplus": round(avg_surplus, 2),
        "prospect_count": prospect_count,
    }


def _compute_revenue_over_time(qs, mode, tier_percent, ars_tier_percent):
    trunc_map = {"daily": TruncDay, "monthly": TruncMonth, "yearly": TruncYear}
    trunc_fn = trunc_map.get(mode, TruncDay)

    rows = (
        qs.filter(qualification_date__isnull=False)
        .annotate(period=trunc_fn("qualification_date"))
        .values("period")
        .annotate(total_surplus=Sum("surplus_amount"))
        .order_by("period")
    )

    labels = []
    surplus_data = []
    revenue_data = []
    ars_data = []

    fmt = {"daily": "%Y-%m-%d", "monthly": "%Y-%m", "yearly": "%Y"}.get(mode, "%Y-%m-%d")

    for r in rows:
        p = r["period"]
        if p is None:
            continue
        labels.append(p.strftime(fmt))
        s = float(r["total_surplus"] or 0)
        rev = s * tier_percent / 100
        ars = rev * ars_tier_percent / 100
        surplus_data.append(round(s, 2))
        revenue_data.append(round(rev, 2))
        ars_data.append(round(ars, 2))

    return {
        "labels": labels,
        "datasets": {
            "total_surplus": surplus_data,
            "ss_revenue": revenue_data,
            "ars_payout": ars_data,
        },
    }


def _compute_county_breakdown(qs, tier_percent, ars_tier_percent):
    rows = (
        qs.values("county__name")
        .annotate(total_surplus=Sum("surplus_amount"))
        .order_by("-total_surplus")[:15]
    )
    labels = []
    ss_revenue = []
    ars_payout = []
    for r in rows:
        labels.append(r["county__name"] or "Unknown")
        s = float(r["total_surplus"] or 0)
        rev = s * tier_percent / 100
        ars = rev * ars_tier_percent / 100
        ss_revenue.append(round(rev, 2))
        ars_payout.append(round(ars, 2))
    return {"labels": labels, "ss_revenue": ss_revenue, "ars_payout": ars_payout}


def _compute_type_distribution(qs, tier_percent):
    rows = (
        qs.values("prospect_type")
        .annotate(total_surplus=Sum("surplus_amount"))
        .order_by("prospect_type")
    )
    labels = []
    surplus = []
    ss_revenue = []
    for r in rows:
        pt = r["prospect_type"]
        labels.append(TYPE_MAP.get(pt, pt))
        s = float(r["total_surplus"] or 0)
        surplus.append(round(s, 2))
        ss_revenue.append(round(s * tier_percent / 100, 2))
    return {"labels": labels, "surplus": surplus, "ss_revenue": ss_revenue}


def _compute_user_revenue(qs, tier_percent, global_ars_tier):
    rows = (
        qs.filter(assigned_to__isnull=False)
        .values("assigned_to__id", "assigned_to__username", "assigned_to__first_name", "assigned_to__last_name")
        .annotate(total_surplus=Sum("surplus_amount"))
        .order_by("-total_surplus")
    )

    # Pre-fetch user ARS tiers
    user_ids = [r["assigned_to__id"] for r in rows]
    profiles = {
        p.user_id: p.ars_tier_percent
        for p in UserProfile.objects.filter(user_id__in=user_ids)
    }

    labels = []
    surplus = []
    ss_revenue = []
    ars_payout = []
    ss_benefit = []

    for r in rows:
        uid = r["assigned_to__id"]
        first = r["assigned_to__first_name"] or ""
        last = r["assigned_to__last_name"] or ""
        name = f"{first} {last}".strip() or r["assigned_to__username"]
        labels.append(name)
        s = float(r["total_surplus"] or 0)
        rev = s * tier_percent / 100
        user_ars = profiles.get(uid, global_ars_tier)
        ars = rev * user_ars / 100
        surplus.append(round(s, 2))
        ss_revenue.append(round(rev, 2))
        ars_payout.append(round(ars, 2))
        ss_benefit.append(round(rev - ars, 2))

    return {
        "labels": labels,
        "surplus": surplus,
        "ss_revenue": ss_revenue,
        "ars_payout": ars_payout,
        "ss_benefit": ss_benefit,
    }


def _compute_threshold_distribution(qs, t1, t2, t3):
    counts = [
        qs.filter(surplus_amount__lt=t1).count(),
        qs.filter(surplus_amount__gte=t1, surplus_amount__lt=t2).count(),
        qs.filter(surplus_amount__gte=t2, surplus_amount__lt=t3).count(),
        qs.filter(surplus_amount__gte=t3).count(),
    ]
    labels = [
        f"< ${t1:,.0f}",
        f"${t1:,.0f} – ${t2:,.0f}",
        f"${t2:,.0f} – ${t3:,.0f}",
        f"> ${t3:,.0f}",
    ]
    return {"labels": labels, "counts": counts}


def _parse_request_params(request):
    """Parse GET params from the request into a standard dict."""
    today = timezone.localdate()
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    try:
        start = date.fromisoformat(start_str) if start_str else today - timedelta(days=29)
    except (ValueError, TypeError):
        start = today - timedelta(days=29)
    try:
        end = date.fromisoformat(end_str) if end_str else today
    except (ValueError, TypeError):
        end = today

    prospect_types_raw = request.GET.get("prospect_type", "")
    prospect_types = [t.strip() for t in prospect_types_raw.split(",") if t.strip()] if prospect_types_raw else []

    return {
        "start": start,
        "end": end,
        "mode": request.GET.get("mode", "daily"),
        "state": request.GET.get("state") or None,
        "county": request.GET.get("county") or None,
        "prospect_types": prospect_types or None,
        "qualification_status": request.GET.get("qualification_status", "qualified"),
    }


class FinanceDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start = today - timedelta(days=29)

        settings = SSRevenueSetting.get_solo()
        tier = settings.tier_percent
        ars_tier = settings.ars_tier_percent
        t1 = float(settings.surplus_threshold_1)
        t2 = float(settings.surplus_threshold_2)
        t3 = float(settings.surplus_threshold_3)

        params = {
            "start": start,
            "end": today,
            "state": None,
            "county": None,
            "prospect_types": None,
            "qualification_status": "qualified",
        }
        qs = _build_base_qs(params)

        ctx["kpi"] = _compute_kpi(qs, tier, ars_tier)
        ctx["revenue_over_time"] = _compute_revenue_over_time(qs, "daily", tier, ars_tier)
        ctx["county_breakdown"] = _compute_county_breakdown(qs, tier, ars_tier)
        ctx["type_distribution"] = _compute_type_distribution(qs, tier)
        ctx["user_revenue"] = _compute_user_revenue(qs, tier, ars_tier)
        ctx["threshold_distribution"] = _compute_threshold_distribution(qs, t1, t2, t3)

        ctx["settings_info"] = {"tier_percent": tier, "ars_tier_percent": ars_tier}
        ctx["start_date"] = start.isoformat()
        ctx["end_date"] = today.isoformat()

        # Filter options
        state_ids = County.objects.filter(prospects__isnull=False).values_list("state_id", flat=True).distinct()
        states = list(State.objects.filter(id__in=state_ids).values("id", "name", "abbreviation").order_by("name"))
        prospect_types = [{"code": code, "label": label} for code, label in Prospect.PROSPECT_TYPES]

        ctx["filter_options"] = {
            "states": states,
            "prospect_types": prospect_types,
        }

        return ctx


class FinanceDataAPI(LoginRequiredMixin, View):
    def get(self, request):
        params = _parse_request_params(request)
        mode = params["mode"]

        settings = SSRevenueSetting.get_solo()
        tier = settings.tier_percent
        ars_tier = settings.ars_tier_percent
        t1 = float(settings.surplus_threshold_1)
        t2 = float(settings.surplus_threshold_2)
        t3 = float(settings.surplus_threshold_3)

        qs = _build_base_qs(params)

        data = {
            "kpi": _compute_kpi(qs, tier, ars_tier),
            "revenue_over_time": _compute_revenue_over_time(qs, mode, tier, ars_tier),
            "county_breakdown": _compute_county_breakdown(qs, tier, ars_tier),
            "type_distribution": _compute_type_distribution(qs, tier),
            "user_revenue": _compute_user_revenue(qs, tier, ars_tier),
            "threshold_distribution": _compute_threshold_distribution(qs, t1, t2, t3),
            "start": params["start"].isoformat(),
            "end": params["end"].isoformat(),
            "mode": mode,
        }
        return JsonResponse(data)


class FinanceCountiesAPI(LoginRequiredMixin, View):
    def get(self, request):
        state_id = request.GET.get("state")
        if not state_id:
            return JsonResponse({"counties": []})

        county_ids = (
            Prospect.objects.filter(county__state_id=state_id)
            .values_list("county_id", flat=True)
            .distinct()
        )
        counties = list(
            County.objects.filter(id__in=county_ids)
            .values("id", "name")
            .order_by("name")
        )
        return JsonResponse({"counties": counties})
