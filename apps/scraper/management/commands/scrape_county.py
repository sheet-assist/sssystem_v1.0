from datetime import datetime

from django.core.management.base import BaseCommand

from apps.locations.models import County
from apps.scraper.engine import run_scrape_job
from apps.scraper.models import ScrapeJob


class Command(BaseCommand):
    help = "Scrape auctions for a county. Supports single date or date range."

    def add_arguments(self, parser):
        parser.add_argument("--county", type=str, required=True, help="County slug (e.g., miami-dade)")
        parser.add_argument("--date", type=str, required=True, help="Start date (YYYY-MM-DD)")
        parser.add_argument("--end-date", type=str, default=None, help="End date inclusive (YYYY-MM-DD). Omit for single date.")
        parser.add_argument("--type", type=str, default="TD", choices=["TD", "TL", "SS", "MF"], help="Prospect type")

    def handle(self, *args, **options):
        try:
            county = County.objects.get(slug=options["county"])
        except County.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"County '{options['county']}' not found"))
            return

        try:
            start = datetime.strptime(options["date"], "%Y-%m-%d").date()
        except ValueError:
            self.stdout.write(self.style.ERROR("Invalid date format. Use YYYY-MM-DD"))
            return

        end = None
        if options["end_date"]:
            try:
                end = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(self.style.ERROR("Invalid end-date format. Use YYYY-MM-DD"))
                return

        date_desc = str(start) if not end else f"{start} to {end}"
        job_name = f"{county.name} {options['type']} {date_desc}"

        job = ScrapeJob.objects.create(
            name=job_name,
            county=county,
            job_type=options["type"],
            target_date=start,
            end_date=end,
            status="pending",
        )
        self.stdout.write(f"Running job {job.pk} for {county.name} [{date_desc}]")

        try:
            run_scrape_job(job)
            self.stdout.write(self.style.SUCCESS(
                f"Done: {job.prospects_created} created, "
                f"{job.prospects_updated} updated, "
                f"{job.prospects_qualified} qualified"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Scrape failed: {e}"))
