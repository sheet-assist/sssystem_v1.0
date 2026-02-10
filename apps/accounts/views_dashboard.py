from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.views.generic import TemplateView

from apps.cases.models import Case, CaseActionLog
from apps.prospects.models import Prospect, ProspectActionLog
from apps.scraper.models import ScrapeJob


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

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
