from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.scraper.engine import run_scrape_job
from apps.scraper.models import ScrapeJob


class Command(BaseCommand):
    help = (
        "Run legacy ScrapeJob batches by name. "
        "Provide one or more job names to target specific groups, "
        "or omit names to run all active jobs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "job_names",
            nargs="*",
            help="Optional list of job names to run. If omitted, all active jobs run.",
        )

    def handle(self, *args, **options):
        job_names = [name.strip() for name in options.get("job_names", []) if name.strip()]
        queryset = self._build_queryset(job_names)

        if not queryset.exists():
            self.stdout.write(self.style.WARNING("No matching ScrapeJobs found."))
            return

        jobs_by_name = defaultdict(list)
        for job in queryset:
            jobs_by_name[job.name or "Untitled Job"].append(job)

        started = 0
        skipped = 0

        for display_name in sorted(jobs_by_name.keys()):
            grouped_jobs = jobs_by_name[display_name]
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"Running group '{display_name}' ({len(grouped_jobs)} job(s))"
                )
            )

            for job in grouped_jobs:
                if job.status == "running":
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"- Job #{job.pk} already running; skipping."))
                    continue

                self._reset_if_needed(job)

                self.stdout.write(
                    f"- Executing job #{job.pk} for {job.county.name}"
                )
                try:
                    run_scrape_job(job)
                    started += 1
                except Exception as exc:  # pragma: no cover - surface errors in CLI output
                    skipped += 1
                    job.refresh_from_db()
                    job.status = "failed"
                    job.error_message = str(exc)
                    job.save(update_fields=["status", "error_message"])
                    self.stderr.write(self.style.ERROR(f"  Failed: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"Finished. Started {started} job(s); skipped {skipped}.")
        )

    def _build_queryset(self, job_names):
        qs = ScrapeJob.objects.select_related("county", "county__state")
        if job_names:
            return qs.filter(name__in=job_names)
        return qs.exclude(status="completed")

    def _reset_if_needed(self, job):
        if job.status in ("failed", "completed"):
            job.status = "pending"
            job.error_message = ""
            job.prospects_created = 0
            job.prospects_updated = 0
            job.prospects_qualified = 0
            job.prospects_disqualified = 0
            job.started_at = None
            job.completed_at = None
            job.save(
                update_fields=[
                    "status",
                    "error_message",
                    "prospects_created",
                    "prospects_updated",
                    "prospects_qualified",
                    "prospects_disqualified",
                    "started_at",
                    "completed_at",
                ]
            )
