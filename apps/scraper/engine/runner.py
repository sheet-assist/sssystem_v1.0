"""Threaded runner that orchestrates scraper jobs."""

import asyncio
import threading
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone

from apps.scraper.models import ScrapeLog

from .data_pipeline import collect_scraped_data, persist_scraped_data
from .url_utils import get_base_url


def run_scrape_job(job):
    """Execute a ScrapeJob in a dedicated thread and bubble up failures."""
    error_holder = {}

    def worker():
        close_old_connections()
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass

        try:
            _run_scrape_job_impl(job)
        except Exception as exc:  # pragma: no cover
            error_holder["error"] = exc
        finally:
            close_old_connections()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join()

    if "error" in error_holder:
        raise error_holder["error"]


def _run_scrape_job_impl(job):
    """Actual scrape job implementation separated from thread bootstrapping."""
    print(f"Starting scrape job {job.pk} for {job.county} {job.job_type} on {job.target_date}")
    job.status = "running"
    job.started_at = timezone.now()
    job.save()

    def log_fn(level, message, raw_html=""):
        ScrapeLog.objects.create(
            job=job,
            level=level,
            message=message,
            raw_html=raw_html[:5000] if raw_html else "",
        )

    try:
        county = job.county
        base_url = get_base_url(county, job.job_type)
        print(f"Using base URL: {base_url}")

        start_date = job.target_date
        end_date = job.end_date or job.target_date
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

        scraped_items = collect_scraped_data(job, dates, base_url, log_fn)
        stats = persist_scraped_data(job, scraped_items)

        job.status = "completed"
        job.prospects_created = stats["created"]
        job.prospects_updated = stats["updated"]
        job.prospects_qualified = stats["qualified"]
        job.prospects_disqualified = stats["disqualified"]
        job.completed_at = timezone.now()
        job.save()

        county.update_last_scraped()
        log_fn(
            "info",
            (
                f"Completed: {stats['created']} created, {stats['updated']} updated, "
                f"{stats['qualified']} qualified"
            ),
        )

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        raise
