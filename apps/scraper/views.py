import threading

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.accounts.mixins import AdminRequiredMixin

from .engine import run_scrape_job
from .forms import ScrapeJobForm
from .models import ScrapeJob, ScrapeLog


class ScraperDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "scraper/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recent_jobs"] = ScrapeJob.objects.select_related("county", "triggered_by")[:10]
        ctx["running_jobs"] = ScrapeJob.objects.filter(status="running").count()
        ctx["total_jobs"] = ScrapeJob.objects.count()
        return ctx


class ScrapeJobListView(AdminRequiredMixin, ListView):
    model = ScrapeJob
    template_name = "scraper/job_list.html"
    paginate_by = 25

    def get_queryset(self):
        qs = ScrapeJob.objects.select_related("county", "county__state", "triggered_by")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = ScrapeJob.JOB_STATUS
        ctx["current_status"] = self.request.GET.get("status", "")
        return ctx


class ScrapeJobCreateView(AdminRequiredMixin, CreateView):
    model = ScrapeJob
    form_class = ScrapeJobForm
    template_name = "scraper/job_create.html"

    def form_valid(self, form):
        form.instance.triggered_by = self.request.user
        form.instance.status = "pending"
        resp = super().form_valid(form)
        messages.success(self.request, f"Scrape job #{self.object.pk} created.")
        return resp

    def get_success_url(self):
        return reverse("scraper:job_detail", kwargs={"pk": self.object.pk})


class ScrapeJobDetailView(AdminRequiredMixin, DetailView):
    model = ScrapeJob
    template_name = "scraper/job_detail.html"

    def get_queryset(self):
        return ScrapeJob.objects.select_related("county", "county__state", "triggered_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = ScrapeLog.objects.filter(job=self.object).order_by("-created_at")[:50]
        return ctx


class ScrapeJobRunView(AdminRequiredMixin, DetailView):
    """Run a pending/failed job in a background thread."""
    model = ScrapeJob

    def post(self, request, *args, **kwargs):
        job = self.get_object()
        if job.status == "running":
            messages.warning(request, "Job is already running.")
            return redirect("scraper:job_detail", pk=job.pk)

        # Reset if re-running a failed job
        if job.status in ("failed", "completed"):
            job.status = "pending"
            job.error_message = ""
            job.prospects_created = 0
            job.prospects_updated = 0
            job.prospects_qualified = 0
            job.prospects_disqualified = 0
            job.save()

        # Run in background thread
        thread = threading.Thread(target=_run_job_safe, args=(job.pk,), daemon=True)
        thread.start()

        messages.success(request, f"Job #{job.pk} started in background.")
        return redirect("scraper:job_detail", pk=job.pk)


def _run_job_safe(job_pk):
    """Wrapper to run job with fresh DB connection in thread."""
    from django.db import connection
    try:
        job = ScrapeJob.objects.get(pk=job_pk)
        run_scrape_job(job)
    except Exception:
        pass
    finally:
        connection.close()
