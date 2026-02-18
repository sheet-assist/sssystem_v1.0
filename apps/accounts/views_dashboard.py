import calendar
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.db.models import DateField
from django.db.models.functions import Cast, Coalesce, TruncDay, TruncMonth, TruncYear
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.cases.models import Case, CaseActionLog
from apps.prospects.models import Prospect, ProspectActionLog
from apps.scraper.models import ScrapeJob
from apps.settings_app.models import SSRevenueSetting


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    @staticmethod
    def _build_conversion_kpi(case_qs, trunc_fn, date_format):
        dated_cases = case_qs.annotate(
            signed_date=Coalesce("contract_date", Cast("created_at", DateField()))
        ).annotate(period=trunc_fn("signed_date"))

        grouped = (
            dated_cases.values("period", "assigned_to__username")
            .annotate(
                total_cases=Count("id"),
                signed_deals=Count("id", filter=Q(status="closed_won")),
            )
            .order_by("period", "assigned_to__username")
        )

        labels = []
        user_series = {}
        details = {}

        for row in grouped:
            period = row["period"]
            if period is None:
                continue
            label = period.strftime(date_format)
            if label not in labels:
                labels.append(label)
            username = row["assigned_to__username"] or "Unassigned"
            if username not in user_series:
                user_series[username] = {}
            if username not in details:
                details[username] = {}
            total_cases = row["total_cases"] or 0
            signed_deals = row["signed_deals"] or 0
            rate = round((signed_deals / total_cases * 100), 1) if total_cases else 0
            user_series[username][label] = rate
            details[username][label] = {
                "assigned": total_cases,
                "converted": signed_deals,
                "conversion_rate": rate,
            }

        datasets = []
        for username, series in sorted(user_series.items()):
            datasets.append(
                {
                    "label": username,
                    "data": [series.get(label, 0) for label in labels],
                }
            )

        return {"labels": labels, "datasets": datasets, "details": details}

    @staticmethod
    def _build_prospect_conversion_kpi(prospect_qs, trunc_fn, date_format):
        assigned_grouped = (
            prospect_qs.filter(assigned_to__isnull=False, assigned_at__isnull=False)
            .annotate(period=trunc_fn("assigned_at"))
            .values("period", "assigned_to__username")
            .annotate(assigned_count=Count("id"))
            .order_by("period", "assigned_to__username")
        )
        converted_grouped = (
            prospect_qs.filter(
                assigned_to__isnull=False,
                assigned_at__isnull=False,
                workflow_status="converted",
            )
            .annotate(period=trunc_fn("assigned_at"))
            .values("period", "assigned_to__username")
            .annotate(converted_count=Count("id"))
            .order_by("period", "assigned_to__username")
        )

        data_map = {}

        for row in assigned_grouped:
            period = row["period"]
            username = row["assigned_to__username"]
            if period is None or not username:
                continue
            label = period.strftime(date_format)
            key = (label, username)
            data_map.setdefault(key, {"assigned": 0, "converted": 0})
            data_map[key]["assigned"] = row["assigned_count"] or 0

        for row in converted_grouped:
            period = row["period"]
            username = row["assigned_to__username"]
            if period is None or not username:
                continue
            label = period.strftime(date_format)
            key = (label, username)
            data_map.setdefault(key, {"assigned": 0, "converted": 0})
            data_map[key]["converted"] = row["converted_count"] or 0

        labels = sorted({label for (label, _username) in data_map.keys()})
        users = sorted({username for (_label, username) in data_map.keys()})

        details = {}
        datasets = []
        for username in users:
            details[username] = {}
            data_points = []
            for label in labels:
                row = data_map.get((label, username), {"assigned": 0, "converted": 0})
                assigned = row["assigned"]
                converted = row["converted"]
                rate = round((converted / assigned) * 100, 1) if assigned else 0
                details[username][label] = {
                    "assigned": assigned,
                    "converted": converted,
                    "conversion_rate": rate,
                }
                data_points.append(rate)
            datasets.append({"label": username, "data": data_points})

        return {"labels": labels, "datasets": datasets, "details": details}

    @staticmethod
    def _build_daily_qualified(prospect_qs, start_date, end_date):
        """Return daily qualified/disqualified counts between start_date and end_date."""
        qualified_rows = (
            prospect_qs.filter(
                qualification_date__date__gte=start_date,
                qualification_date__date__lte=end_date,
            )
            .annotate(day=TruncDay("qualification_date"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        disqualified_rows = (
            prospect_qs.filter(
                disqualification_date__date__gte=start_date,
                disqualification_date__date__lte=end_date,
            )
            .annotate(day=TruncDay("disqualification_date"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        day_counts = {
            row["day"].date().isoformat(): row["count"]
            for row in qualified_rows
            if row.get("day")
        }
        disqualified_day_counts = {
            row["day"].date().isoformat(): row["count"]
            for row in disqualified_rows
            if row.get("day")
        }
        labels = []
        qualified_counts = []
        disqualified_counts = []
        num_days = (end_date - start_date).days + 1
        for offset in range(num_days):
            day = start_date + timedelta(days=offset)
            key = day.isoformat()
            labels.append(key)
            qualified_counts.append(day_counts.get(key, 0))
            disqualified_counts.append(disqualified_day_counts.get(key, 0))
        return {
            "labels": labels,
            "qualified_counts": qualified_counts,
            "disqualified_counts": disqualified_counts,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        profile = getattr(user, "profile", None)
        is_admin = user.is_superuser or (profile and profile.is_admin)

        # --- Prospect stats ---
        prospect_qs = Prospect.objects.all()
        ctx["total_prospects"] = prospect_qs.count()
        ctx["qualified_count"] = prospect_qs.filter(qualification_status="qualified").count()
        ctx["disqualified_count"] = prospect_qs.filter(qualification_status="disqualified").count()
        ctx["pending_count"] = prospect_qs.filter(qualification_status="pending").count()
        qualified_surplus = (
            prospect_qs.filter(qualification_status="qualified")
            .aggregate(total=Sum("surplus_amount"))
            .get("total")
        ) or 0
        ss_revenue_tier = SSRevenueSetting.get_solo().tier_percent
        ctx["qualified_surplus_amount"] = qualified_surplus
        ctx["total_revenue"] = (qualified_surplus * ss_revenue_tier) / 100
        ctx["ss_revenue_tier"] = ss_revenue_tier
        # Daily qualified trend (last 30 days)
        today = timezone.localdate()
        start_date = today - timedelta(days=29)
        ctx["daily_qualified_chart"] = self._build_daily_qualified(
            prospect_qs, start_date, today
        )

        # Pipeline by workflow_status — list of (label, count) for template
        pipeline_dict = {}
        for item in (
            prospect_qs
            .values("workflow_status")
            .annotate(count=Count("id"))
        ):
            pipeline_dict[item["workflow_status"]] = item["count"]
        ctx["pipeline"] = [
            (label, pipeline_dict.get(code, 0))
            for code, label in Prospect.WORKFLOW_STATUS
        ]

        # Touched vs Untouched
        ctx["touched_count"] = prospect_qs.exclude(workflow_status="new").count()
        ctx["untouched_count"] = prospect_qs.filter(workflow_status="new").count()

        # --- Case stats ---
        case_qs = Case.objects.all()
        ctx["total_cases"] = case_qs.count()
        ctx["active_cases"] = case_qs.filter(status="active").count()
        ctx["closed_won"] = case_qs.filter(status="closed_won").count()
        ctx["closed_lost"] = case_qs.filter(status="closed_lost").count()

        # Conversion rate
        converted = prospect_qs.filter(workflow_status="converted").count()
        ctx["converted_count"] = converted
        ctx["conversion_rate"] = (
            round(converted / ctx["total_prospects"] * 100, 1)
            if ctx["total_prospects"] > 0 else 0
        )

        # User performance KPI: case-to-signed-deal conversion by period
        signed_case_qs = case_qs.exclude(assigned_to__isnull=True)
        ctx["conversion_kpi"] = {
            "daily": self._build_conversion_kpi(signed_case_qs, TruncDay, "%Y-%m-%d"),
            "monthly": self._build_conversion_kpi(signed_case_qs, TruncMonth, "%Y-%m"),
            "yearly": self._build_conversion_kpi(signed_case_qs, TruncYear, "%Y"),
        }

        # Prospect conversion KPI by assigned user:
        # converted = assigned prospect with workflow_status="converted"
        ctx["prospect_conversion_kpi"] = {
            "daily": self._build_prospect_conversion_kpi(prospect_qs, TruncDay, "%Y-%m-%d"),
            "monthly": self._build_prospect_conversion_kpi(prospect_qs, TruncMonth, "%Y-%m"),
            "yearly": self._build_prospect_conversion_kpi(prospect_qs, TruncYear, "%Y"),
        }

        # --- Scraper stats (admin only) ---
        if is_admin:
            ctx["last_scrape_job"] = ScrapeJob.objects.order_by("-created_at").first()
            ctx["running_jobs"] = ScrapeJob.objects.filter(status="running").count()
            ctx["total_scrape_jobs"] = ScrapeJob.objects.count()

        # --- Recent activity (last 15 actions) ---
        prospect_logs = ProspectActionLog.objects.select_related("prospect", "user").order_by("-created_at")[:10]
        case_logs = CaseActionLog.objects.select_related("case", "user").order_by("-created_at")[:10]

        # Merge and sort
        activity = []
        for log in prospect_logs:
            activity.append({
                "time": log.created_at,
                "type": "prospect",
                "action": log.get_action_type_display(),
                "description": log.description,
                "user": log.user,
                "ref": f"Prospect {log.prospect.case_number}",
                "url": f"/prospects/detail/{log.prospect.pk}/",
            })
        for log in case_logs:
            activity.append({
                "time": log.created_at,
                "type": "case",
                "action": log.action_type,
                "description": log.description,
                "user": log.user,
                "ref": f"Case {log.case.case_number or log.case.pk}",
                "url": f"/cases/{log.case.pk}/",
            })
        activity.sort(key=lambda x: x["time"], reverse=True)
        ctx["recent_activity"] = activity[:15]

        # --- User-specific stats ---
        if not is_admin:
            ctx["my_prospects"] = prospect_qs.filter(assigned_to=user).count()
            ctx["my_cases"] = case_qs.filter(assigned_to=user).count()

        ctx["is_admin"] = is_admin
        return ctx


class DailyQualifiedChartAPI(LoginRequiredMixin, View):
    """Return daily qualified chart data as JSON for a given date range."""

    def get(self, request):
        today = timezone.localdate()
        mode = request.GET.get("mode", "30days")  # '30days' or 'month'

        if mode == "month":
            # Parse year/month, default to current
            try:
                year = int(request.GET.get("year", today.year))
                month = int(request.GET.get("month", today.month))
            except (ValueError, TypeError):
                year, month = today.year, today.month
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)
            # Cap end_date at today
            if end_date > today:
                end_date = today
            period_label = start_date.strftime("%B %Y")
        else:
            # 30-day sliding window
            try:
                start_date = date.fromisoformat(request.GET.get("start", ""))
                end_date = date.fromisoformat(request.GET.get("end", ""))
            except (ValueError, TypeError):
                end_date = today
                start_date = end_date - timedelta(days=29)
            # Cap end_date at today
            if end_date > today:
                end_date = today
                start_date = end_date - timedelta(days=29)
            period_label = f"{start_date.strftime('%b %d, %Y')} \u2013 {end_date.strftime('%b %d, %Y')}"

        prospect_qs = Prospect.objects.all()
        data = DashboardView._build_daily_qualified(prospect_qs, start_date, end_date)
        data["start"] = start_date.isoformat()
        data["end"] = end_date.isoformat()
        data["period_label"] = period_label
        data["mode"] = mode
        data["is_latest"] = end_date >= today
        return JsonResponse(data)
