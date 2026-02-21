"""Management command: run ScrapeJob batches.

All run parameters are read from the JSON config file
(default: apps/scraper/config/scrape_jobs_config.json).
Edit that file to specify which job names to run.
An empty job_names list runs all active jobs.

Usage:
    python manage.py run_scrape_jobs
    python manage.py run_scrape_jobs --config path/to/other_config.json
"""

import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.scraper.engine import run_scrape_job
from apps.scraper.models import ScrapeJob

BASE_DIR = Path(settings.BASE_DIR)
DEFAULT_CONFIG_PATH = BASE_DIR / "apps" / "scraper" / "config" / "scrape_jobs_config.json"


def load_config(path):
    """Load JSON config file; return empty dict if file is missing or unreadable."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Warning: could not load config file {path}: {exc}")
        return {}


class Command(BaseCommand):
    help = "Run ScrapeJob batches. Job names are read from apps/scraper/config/scrape_jobs_config.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            default=str(DEFAULT_CONFIG_PATH),
            metavar="PATH",
            help="Path to JSON config file (default: apps/scraper/config/scrape_jobs_config.json)",
        )

    def handle(self, *args, **options):
        cfg = load_config(options["config"])
        job_names = [n.strip() for n in (cfg.get("job_names") or []) if n.strip()]

        queryset = self._build_queryset(job_names)

        if not queryset.exists():
            self.stdout.write(self.style.WARNING("No matching ScrapeJobs found."))
            return

        if job_names:
            self.stdout.write(f"Running jobs: {', '.join(job_names)}")
        else:
            self.stdout.write("Running all active jobs.")

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

                self.stdout.write(f"- Executing job #{job.pk} for {job.county.name}")
                try:
                    run_scrape_job(job)
                    started += 1
                except Exception as exc:
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
