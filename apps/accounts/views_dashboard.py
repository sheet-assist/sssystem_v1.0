import calendar
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum, Min, Max
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
    def _resolve_cards_period(request):
        today = timezone.localdate()
        mode = request.GET.get("cards_mode", "all")
        if mode not in {"all", "30days", "month"}:
            mode = "all"

        start_date = None
        end_date = None
        period_label = "All Time"
        prev_query = ""
        next_query = ""
        is_latest = True

        if mode == "month":
            try:
                year = int(request.GET.get("cards_year", today.year))
                month = int(request.GET.get("cards_month", today.month))
            except (ValueError, TypeError):
                year, month = today.year, today.month
            month = min(max(month, 1), 12)
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)
            period_label = start_date.strftime("%B %Y")
            prev_month = (start_date - timedelta(days=1)).replace(day=1)
            next_month = (end_date + timedelta(days=1)).replace(day=1)
            prev_query = urlencode({"cards_mode": "month", "cards_year": prev_month.year, "cards_month": prev_month.month})
            next_query = urlencode({"cards_mode": "month", "cards_year": next_month.year, "cards_month": next_month.month})
            is_latest = (year == today.year and month == today.month)
        elif mode == "30days":
            try:
                start_date = date.fromisoformat(request.GET.get("cards_start", ""))
                end_date = date.fromisoformat(request.GET.get("cards_end", ""))
            except (ValueError, TypeError):
                end_date = today
                start_date = end_date - timedelta(days=29)
            if end_date > today:
                end_date = today
            if start_date > end_date:
                start_date = end_date - timedelta(days=29)
            period_label = f"{start_date.strftime('%b %d, %Y')} \u2013 {end_date.strftime('%b %d, %Y')}"
            prev_end = start_date - timedelta(days=1)
            prev_start = prev_end - timedelta(days=29)
            next_start = end_date + timedelta(days=1)
            next_end = next_start + timedelta(days=29)
            prev_query = urlencode({"cards_mode": "30days", "cards_start": prev_start.isoformat(), "cards_end": prev_end.isoformat()})
            next_query = urlencode({"cards_mode": "30days", "cards_start": next_start.isoformat(), "cards_end": next_end.isoformat()})
            is_latest = end_date >= today

        return {
            "mode": mode,
            "start_date": start_date,
            "end_date": end_date,
            "period_label": period_label,
            "prev_query": prev_query,
            "next_query": next_query,
            "is_latest": is_latest,
            "all_query": urlencode({"cards_mode": "all"}),
            "mode_30_query": urlencode({"cards_mode": "30days"}),
            "mode_month_query": urlencode({"cards_mode": "month", "cards_year": today.year, "cards_month": today.month}),
        }

    @staticmethod
    def _build_cards_stats(cards_start, cards_end, is_admin, ss_revenue_tier):
        prospect_qs = Prospect.objects.all()
        if cards_start and cards_end:
            prospect_qs = prospect_qs.filter(
                Q(qualification_date__date__gte=cards_start, qualification_date__date__lte=cards_end)
                | Q(disqualification_date__date__gte=cards_start, disqualification_date__date__lte=cards_end)
                | Q(
                    qualification_status="pending",
                    created_at__date__gte=cards_start,
                    created_at__date__lte=cards_end,
                )
            )

        data = {}
        auction_range = prospect_qs.aggregate(
            first_auction=Min("auction_date"),
            last_auction=Max("auction_date"),
        )
        first_auction = auction_range.get("first_auction")
        last_auction = auction_range.get("last_auction")
        if first_auction and last_auction:
            data["auction_range_label"] = f"{first_auction:%m/%d/%Y} - {last_auction:%m/%d/%Y}"
        elif first_auction:
            data["auction_range_label"] = f"{first_auction:%m/%d/%Y}"
        else:
            data["auction_range_label"] = "-"

        prospect_totals = prospect_qs.aggregate(
            total_prospects=Count("id"),
            qualified_count=Count("id", filter=Q(qualification_status="qualified")),
            disqualified_count=Count("id", filter=Q(qualification_status="disqualified")),
            pending_count=Count("id", filter=Q(qualification_status="pending")),
            qualified_surplus=Sum("surplus_amount", filter=Q(qualification_status="qualified")),
        )
        data["total_prospects"] = prospect_totals.get("total_prospects", 0) or 0
        data["qualified_count"] = prospect_totals.get("qualified_count", 0) or 0
        data["disqualified_count"] = prospect_totals.get("disqualified_count", 0) or 0
        data["pending_count"] = prospect_totals.get("pending_count", 0) or 0
        qualified_surplus = prospect_totals.get("qualified_surplus") or 0
        data["qualified_surplus_amount"] = float(qualified_surplus)

        if is_admin:
            data["total_revenue"] = float((qualified_surplus * ss_revenue_tier) / 100)
            data["ss_revenue_tier"] = float(ss_revenue_tier)
            prospect_type_stats = {
                row["prospect_type"]: row
                for row in (
                    prospect_qs.values("prospect_type")
                    .annotate(
                        prospect_count=Count("id"),
                        qualified_count=Count("id", filter=Q(qualification_status="qualified")),
                        qualified_total_surplus=Sum(
                            "surplus_amount",
                            filter=Q(qualification_status="qualified"),
                        ),
                    )
                )
            }
            data["revenue_distribution_prospects_by_type"] = [
                {
                    "code": code,
                    "prospect_count": prospect_type_stats.get(code, {}).get("prospect_count", 0),
                    "qualified_count": prospect_type_stats.get(code, {}).get("qualified_count", 0),
                    "total_surplus": float(prospect_type_stats.get(code, {}).get("qualified_total_surplus") or 0),
                    "prospect_revenue": float(((prospect_type_stats.get(code, {}).get("qualified_total_surplus") or 0) * ss_revenue_tier) / 100),
                }
                for code, _label in Prospect.PROSPECT_TYPES
            ]

        # Touched/Untouched and compact touched table (qualified only)
        qualified_prospect_qs = prospect_qs.filter(qualification_status="qualified")
        touched_by_type_rows = list(
            qualified_prospect_qs.values("prospect_type")
            .annotate(
                new_count=Count("id", filter=Q(workflow_status="new")),
                in_progress_count=Count(
                    "id",
                    filter=Q(workflow_status__in=["assigned", "researching", "skip_tracing", "contacting", "contract_sent"]),
                ),
                closed_count=Count("id", filter=Q(workflow_status__in=["converted", "dead"])),
            )
        )
        touched_by_type_stats = {
            row["prospect_type"]: row
            for row in touched_by_type_rows
        }
        data["untouched_count"] = sum((row.get("new_count", 0) or 0) for row in touched_by_type_rows)
        data["touched_count"] = sum((row.get("in_progress_count", 0) or 0) + (row.get("closed_count", 0) or 0) for row in touched_by_type_rows)
        data["touched_in_progress_count"] = sum((row.get("in_progress_count", 0) or 0) for row in touched_by_type_rows)
        data["touched_closed_count"] = sum((row.get("closed_count", 0) or 0) for row in touched_by_type_rows)
        data["touched_by_type"] = [
            {
                "code": code,
                "new_count": touched_by_type_stats.get(code, {}).get("new_count", 0),
                "in_progress_count": touched_by_type_stats.get(code, {}).get("in_progress_count", 0),
                "closed_count": touched_by_type_stats.get(code, {}).get("closed_count", 0),
            }
            for code, _label in Prospect.PROSPECT_TYPES
        ]

        # Case card stats
        case_qs = Case.objects.all()
        if cards_start and cards_end:
            case_qs = case_qs.filter(created_at__date__gte=cards_start, created_at__date__lte=cards_end)
        case_totals = case_qs.aggregate(
            total_cases=Count("id"),
            active_cases=Count("id", filter=Q(status="active")),
            closed_won=Count("id", filter=Q(status="closed_won")),
            closed_lost=Count("id", filter=Q(status="closed_lost")),
        )
        data["total_cases"] = case_totals.get("total_cases", 0) or 0
        data["active_cases"] = case_totals.get("active_cases", 0) or 0
        data["closed_won"] = case_totals.get("closed_won", 0) or 0
        data["closed_lost"] = case_totals.get("closed_lost", 0) or 0
        if is_admin:
            case_type_rows = list(
                case_qs.values("case_type")
                .annotate(
                    total_case_count=Count("id"),
                    invoice_paid_count=Count("id", filter=Q(status="invoice_paid")),
                    qualified_total_prospect_amount=Sum(
                        "prospect__surplus_amount",
                        filter=Q(prospect__qualification_status="qualified"),
                    ),
                    qualified_invoice_paid_prospect_amount=Sum(
                        "prospect__surplus_amount",
                        filter=Q(status="invoice_paid", prospect__qualification_status="qualified"),
                    ),
                )
            )
            case_type_stats = {
                row["case_type"]: row
                for row in case_type_rows
            }
            qualified_case_prospect_amount = sum((row.get("qualified_total_prospect_amount") or 0) for row in case_type_rows)
            qualified_invoice_paid_prospect_amount = sum((row.get("qualified_invoice_paid_prospect_amount") or 0) for row in case_type_rows)
            data["case_qualified_prospect_amount"] = float(qualified_case_prospect_amount)
            data["case_revenue"] = float((qualified_case_prospect_amount * ss_revenue_tier) / 100)
            data["invoice_paid_revenue"] = float((qualified_invoice_paid_prospect_amount * ss_revenue_tier) / 100)
            data["revenue_distribution_cases_by_type"] = [
                {
                    "code": code,
                    "total_case_count": case_type_stats.get(code, {}).get("total_case_count", 0),
                    "invoice_paid_count": case_type_stats.get(code, {}).get("invoice_paid_count", 0),
                    "prospect_rev": float(((case_type_stats.get(code, {}).get("qualified_total_prospect_amount") or 0) * ss_revenue_tier) / 100),
                    "invoice_paid_rev": float(((case_type_stats.get(code, {}).get("qualified_invoice_paid_prospect_amount") or 0) * ss_revenue_tier) / 100),
                }
                for code, _label in Case.CASE_TYPE_CHOICES
            ]

        # Conversion card (qualified only)
        qualified_conversion_qs = prospect_qs.filter(qualification_status="qualified")
        qualified_total = qualified_conversion_qs.count()
        converted = qualified_conversion_qs.filter(workflow_status="converted").count()
        data["converted_count"] = converted
        data["conversion_qualified_total"] = qualified_total
        data["conversion_rate"] = round((converted / qualified_total * 100), 1) if qualified_total > 0 else 0
        conversion_by_type_rows = list(
            qualified_conversion_qs.values("prospect_type")
            .annotate(
                total_count=Count("id"),
                converted_count=Count("id", filter=Q(workflow_status="converted")),
            )
        )
        conversion_by_type_stats = {
            row["prospect_type"]: row
            for row in conversion_by_type_rows
        }
        data["conversion_by_type"] = []
        for code, _label in Prospect.PROSPECT_TYPES:
            total_count = conversion_by_type_stats.get(code, {}).get("total_count", 0) or 0
            converted_count = conversion_by_type_stats.get(code, {}).get("converted_count", 0) or 0
            conversion_percent = round((converted_count / total_count) * 100, 1) if total_count else 0
            data["conversion_by_type"].append(
                {
                    "code": code,
                    "count": total_count,
                    "converted_count": converted_count,
                    "conversion_percent": conversion_percent,
                }
            )
        return data

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
        ss_revenue_tier = SSRevenueSetting.get_solo().tier_percent if is_admin else 0
        cards_period = self._resolve_cards_period(self.request)
        cards_start = cards_period["start_date"]
        cards_end = cards_period["end_date"]
        ctx["cards_filter_mode"] = cards_period["mode"]
        ctx["cards_filter_period_label"] = cards_period["period_label"]
        ctx["cards_filter_prev_query"] = cards_period["prev_query"]
        ctx["cards_filter_next_query"] = cards_period["next_query"]
        ctx["cards_filter_is_latest"] = cards_period["is_latest"]
        ctx["cards_filter_all_query"] = cards_period["all_query"]
        ctx["cards_filter_30_query"] = cards_period["mode_30_query"]
        ctx["cards_filter_month_query"] = cards_period["mode_month_query"]
        ctx["cards_filter_start"] = cards_start.isoformat() if cards_start else ""
        ctx["cards_filter_end"] = cards_end.isoformat() if cards_end else ""

        # --- Prospect stats ---
        prospect_qs = Prospect.objects.all()
        if cards_start and cards_end:
            prospect_qs = prospect_qs.filter(
                Q(qualification_date__date__gte=cards_start, qualification_date__date__lte=cards_end)
                | Q(disqualification_date__date__gte=cards_start, disqualification_date__date__lte=cards_end)
                | Q(
                    qualification_status="pending",
                    created_at__date__gte=cards_start,
                    created_at__date__lte=cards_end,
                )
            ).distinct()
        auction_range_ctx = prospect_qs.aggregate(
            first_auction=Min("auction_date"),
            last_auction=Max("auction_date"),
        )
        first_auction_ctx = auction_range_ctx.get("first_auction")
        last_auction_ctx = auction_range_ctx.get("last_auction")
        if first_auction_ctx and last_auction_ctx:
            ctx["auction_range_label"] = f"{first_auction_ctx:%m/%d/%Y} - {last_auction_ctx:%m/%d/%Y}"
        elif first_auction_ctx:
            ctx["auction_range_label"] = f"{first_auction_ctx:%m/%d/%Y}"
        else:
            ctx["auction_range_label"] = "-"
        ctx["total_prospects"] = prospect_qs.count()
        ctx["qualified_count"] = prospect_qs.filter(qualification_status="qualified").count()
        ctx["disqualified_count"] = prospect_qs.filter(qualification_status="disqualified").count()
        ctx["pending_count"] = prospect_qs.filter(qualification_status="pending").count()
        qualified_surplus = (
            prospect_qs.filter(qualification_status="qualified")
            .aggregate(total=Sum("surplus_amount"))
            .get("total")
        ) or 0
        ctx["qualified_surplus_amount"] = qualified_surplus
        if is_admin:
            ctx["total_revenue"] = (qualified_surplus * ss_revenue_tier) / 100
            ctx["ss_revenue_tier"] = ss_revenue_tier
            prospect_type_stats = {
                row["prospect_type"]: row
                for row in (
                    prospect_qs.values("prospect_type")
                    .annotate(
                        prospect_count=Count("id"),
                        qualified_count=Count("id", filter=Q(qualification_status="qualified")),
                        total_surplus=Sum("surplus_amount"),
                        qualified_total_surplus=Sum(
                            "surplus_amount",
                            filter=Q(qualification_status="qualified"),
                        ),
                    )
                )
            }
            ctx["revenue_distribution_prospects_by_type"] = [
                {
                    "code": code,
                    "label": label,
                    "prospect_count": prospect_type_stats.get(code, {}).get("prospect_count", 0),
                    "qualified_count": prospect_type_stats.get(code, {}).get("qualified_count", 0),
                    "total_surplus": prospect_type_stats.get(code, {}).get("qualified_total_surplus") or 0,
                    "prospect_revenue": ((prospect_type_stats.get(code, {}).get("qualified_total_surplus") or 0) * ss_revenue_tier) / 100,
                }
                for code, label in Prospect.PROSPECT_TYPES
            ]
        # Daily qualified trend (last 30 days)
        today = timezone.localdate()
        if cards_start and cards_end:
            start_date = cards_start
            end_date = cards_end
        else:
            start_date = today - timedelta(days=29)
            end_date = today
        ctx["daily_qualified_chart"] = self._build_daily_qualified(
            Prospect.objects.all(), start_date, end_date
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

        # Touched vs Untouched (all qualified prospects, including converted-to-case)
        qualified_prospect_qs = prospect_qs.filter(qualification_status="qualified")
        ctx["touched_count"] = qualified_prospect_qs.exclude(workflow_status="new").count()
        ctx["untouched_count"] = qualified_prospect_qs.filter(workflow_status="new").count()
        touched_by_type_stats = {
            row["prospect_type"]: row
            for row in (
                qualified_prospect_qs.values("prospect_type")
                .annotate(
                    new_count=Count("id", filter=Q(workflow_status="new")),
                    in_progress_count=Count(
                        "id",
                        filter=Q(
                            workflow_status__in=[
                                "assigned",
                                "researching",
                                "skip_tracing",
                                "contacting",
                                "contract_sent",
                            ]
                        ),
                    ),
                    closed_count=Count("id", filter=Q(workflow_status__in=["converted", "dead"])),
                )
            )
        }
        touched_totals = qualified_prospect_qs.aggregate(
            new_count=Count("id", filter=Q(workflow_status="new")),
            in_progress_count=Count(
                "id",
                filter=Q(
                    workflow_status__in=[
                        "assigned",
                        "researching",
                        "skip_tracing",
                        "contacting",
                        "contract_sent",
                    ]
                ),
            ),
            closed_count=Count("id", filter=Q(workflow_status__in=["converted", "dead"])),
        )
        ctx["touched_new_count"] = touched_totals.get("new_count", 0) or 0
        ctx["touched_in_progress_count"] = touched_totals.get("in_progress_count", 0) or 0
        ctx["touched_closed_count"] = touched_totals.get("closed_count", 0) or 0
        ctx["touched_by_type"] = [
            {
                "code": code,
                "new_count": touched_by_type_stats.get(code, {}).get("new_count", 0),
                "in_progress_count": touched_by_type_stats.get(code, {}).get("in_progress_count", 0),
                "closed_count": touched_by_type_stats.get(code, {}).get("closed_count", 0),
            }
            for code, _label in Prospect.PROSPECT_TYPES
        ]

        # --- Case stats ---
        case_qs = Case.objects.all()
        if cards_start and cards_end:
            case_qs = case_qs.filter(created_at__date__gte=cards_start, created_at__date__lte=cards_end)
        ctx["total_cases"] = case_qs.count()
        ctx["active_cases"] = case_qs.filter(status="active").count()
        ctx["closed_won"] = case_qs.filter(status="closed_won").count()
        ctx["closed_lost"] = case_qs.filter(status="closed_lost").count()
        if is_admin:
            case_prospect_amount = (
                case_qs.aggregate(total=Sum("prospect__surplus_amount")).get("total")
            ) or 0
            qualified_case_prospect_amount = (
                case_qs.filter(prospect__qualification_status="qualified")
                .aggregate(total=Sum("prospect__surplus_amount"))
                .get("total")
            ) or 0
            invoice_paid_prospect_amount = (
                case_qs.filter(status="invoice_paid")
                .aggregate(total=Sum("prospect__surplus_amount"))
                .get("total")
            ) or 0
            qualified_invoice_paid_prospect_amount = (
                case_qs.filter(status="invoice_paid", prospect__qualification_status="qualified")
                .aggregate(total=Sum("prospect__surplus_amount"))
                .get("total")
            ) or 0
            ctx["case_prospect_amount"] = case_prospect_amount
            ctx["case_qualified_prospect_amount"] = qualified_case_prospect_amount
            ctx["case_revenue"] = (qualified_case_prospect_amount * ss_revenue_tier) / 100
            ctx["invoice_paid_revenue"] = (qualified_invoice_paid_prospect_amount * ss_revenue_tier) / 100
            case_type_stats = {
                row["case_type"]: row
                for row in (
                    case_qs.values("case_type")
                    .annotate(
                        total_case_count=Count("id"),
                        invoice_paid_count=Count("id", filter=Q(status="invoice_paid")),
                        total_prospect_amount=Sum("prospect__surplus_amount"),
                        qualified_total_prospect_amount=Sum(
                            "prospect__surplus_amount",
                            filter=Q(prospect__qualification_status="qualified"),
                        ),
                        invoice_paid_prospect_amount=Sum(
                            "prospect__surplus_amount",
                            filter=Q(status="invoice_paid"),
                        ),
                        qualified_invoice_paid_prospect_amount=Sum(
                            "prospect__surplus_amount",
                            filter=Q(status="invoice_paid", prospect__qualification_status="qualified"),
                        ),
                    )
                )
            }
            ctx["revenue_distribution_cases_by_type"] = [
                {
                    "code": code,
                    "label": label,
                    "total_case_count": case_type_stats.get(code, {}).get("total_case_count", 0),
                    "invoice_paid_count": case_type_stats.get(code, {}).get("invoice_paid_count", 0),
                    "prospect_rev": ((case_type_stats.get(code, {}).get("qualified_total_prospect_amount") or 0) * ss_revenue_tier) / 100,
                    "invoice_paid_rev": ((case_type_stats.get(code, {}).get("qualified_invoice_paid_prospect_amount") or 0) * ss_revenue_tier) / 100,
                }
                for code, label in Case.CASE_TYPE_CHOICES
            ]

        # Conversion rate (qualified prospects only)
        qualified_conversion_qs = prospect_qs.filter(qualification_status="qualified")
        qualified_total = qualified_conversion_qs.count()
        converted = qualified_conversion_qs.filter(workflow_status="converted").count()
        ctx["converted_count"] = converted
        ctx["conversion_rate"] = (
            round(converted / qualified_total * 100, 1)
            if qualified_total > 0 else 0
        )
        ctx["conversion_qualified_total"] = qualified_total
        conversion_by_type_stats = {
            row["prospect_type"]: row
            for row in (
                qualified_conversion_qs.values("prospect_type")
                .annotate(
                    total_count=Count("id"),
                    converted_count=Count("id", filter=Q(workflow_status="converted")),
                )
            )
        }
        ctx["conversion_by_type"] = []
        for code, label in Prospect.PROSPECT_TYPES:
            total_count = conversion_by_type_stats.get(code, {}).get("total_count", 0) or 0
            converted_count = conversion_by_type_stats.get(code, {}).get("converted_count", 0) or 0
            conversion_percent = round((converted_count / total_count) * 100, 1) if total_count else 0
            ctx["conversion_by_type"].append(
                {
                    "code": code,
                    "label": label,
                    "count": total_count,
                    "converted_count": converted_count,
                    "conversion_percent": conversion_percent,
                }
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


class DashboardCardsStatsAPI(LoginRequiredMixin, View):
    """Return dashboard card stats as JSON for client-side card filter updates."""

    def get(self, request):
        user = request.user
        profile = getattr(user, "profile", None)
        is_admin = user.is_superuser or (profile and profile.is_admin)
        ss_revenue_tier = SSRevenueSetting.get_solo().tier_percent if is_admin else 0
        cards_period = DashboardView._resolve_cards_period(request)
        data = DashboardView._build_cards_stats(
            cards_period["start_date"],
            cards_period["end_date"],
            is_admin,
            ss_revenue_tier,
        )
        data["cards_filter_mode"] = cards_period["mode"]
        data["cards_filter_period_label"] = cards_period["period_label"]
        data["cards_filter_is_latest"] = cards_period["is_latest"]
        data["cards_filter_start"] = cards_period["start_date"].isoformat() if cards_period["start_date"] else ""
        data["cards_filter_end"] = cards_period["end_date"].isoformat() if cards_period["end_date"] else ""
        return JsonResponse(data)
