import platform
import subprocess
from urllib.parse import urlparse

from django.core.management.base import BaseCommand

from apps.locations.models import State
from apps.scraper.models import CountyScrapeURL


class Command(BaseCommand):
    help = (
        "Validate CountyScrapeURL entries for a given state and job type. "
        "Any URL whose host cannot be pinged is marked inactive."
    )

    def add_arguments(self, parser):
        parser.add_argument("state", help="State abbreviation, e.g., FL")
        parser.add_argument(
            "job_type",
            choices=[choice[0] for choice in CountyScrapeURL.URL_TYPE_CHOICES],
            help="Job type to validate (TD, TL, SS, MF)",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=10.0,
            help="Per-request timeout in seconds (default 10)",
        )

    def handle(self, *args, **options):
        state_code = options["state"].upper()
        job_type = options["job_type"]
        timeout = options["timeout"]

        try:
            state = State.objects.get(abbreviation=state_code)
        except State.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"State '{state_code}' not found"))
            return

        queryset = CountyScrapeURL.objects.filter(state=state, url_type=job_type).select_related("county")
        urls = list(queryset)
        if not urls:
            self.stdout.write(self.style.WARNING("No URLs found for given state/type."))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Validating {len(urls)} URL(s) for {state_code} / {job_type}"
            )
        )

        total = len(urls)
        results = []

        for url_obj in urls:
            display = f"{url_obj.county.name} -> {url_obj.base_url}"
            self.stdout.write(f"Checking {display}")

            accessible = self._ping_url(url_obj.base_url, timeout)
            results.append((url_obj, accessible))

            if accessible:
                self.stdout.write(self.style.SUCCESS("  Host reachable"))
            else:
                self.stdout.write(self.style.WARNING("  Ping failed"))

        deactivated = 0
        reactivated = 0
        for url_obj, accessible in results:
            if accessible and not url_obj.is_active:
                self._activate(url_obj)
                reactivated += 1
            elif not accessible and url_obj.is_active:
                self._deactivate(url_obj)
                deactivated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. {reactivated} reactivated, {deactivated} marked inactive, {total} checked."
            )
        )

    def _ping_url(self, url: str, timeout: float) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.split(":", 1)[0] if parsed.netloc else parsed.path
        if not host:
            return False

        timeout_ms = max(int(timeout * 1000), 1000)
        system = platform.system().lower()

        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        else:
            timeout_sec = max(int(timeout), 1)
            cmd = ["ping", "-c", "1", "-W", str(timeout_sec), host]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def _deactivate(self, url_obj: CountyScrapeURL):
        url_obj.is_active = False
        url_obj.save(update_fields=["is_active"])

    def _activate(self, url_obj: CountyScrapeURL):
        url_obj.is_active = True
        url_obj.save(update_fields=["is_active"])
