from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.core.management.base import BaseCommand

from apps.scraper.models import CountyScrapeURL


class Command(BaseCommand):
    help = (
        "Check all URLs in CountyScrapeURL table using Playwright. "
        "Mark URLs as inactive if they fail to load or return errors. "
        "Automatically tries both http and https protocols."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=30000,
            help="Page load timeout in milliseconds (default 30000)",
        )
        parser.add_argument(
            "--state",
            type=str,
            help="Optional: Only check URLs for a specific state (e.g., FL)",
        )
        parser.add_argument(
            "--county",
            type=str,
            help="Optional: Only check URLs for a specific county (e.g., Volusia)",
        )
        parser.add_argument(
            "--url-type",
            type=str,
            choices=[choice[0] for choice in CountyScrapeURL.URL_TYPE_CHOICES],
            help="Optional: Only check URLs of a specific type (TD, TL, SS, MF)",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        state_filter = options.get("state")
        county_filter = options.get("county")
        url_type_filter = options.get("url_type")

        # Build queryset with optional filters
        queryset = CountyScrapeURL.objects.select_related("county", "state")
        
        if state_filter:
            queryset = queryset.filter(state__abbreviation=state_filter.upper())
        
        if county_filter:
            queryset = queryset.filter(county__name__icontains=county_filter)
        
        if url_type_filter:
            queryset = queryset.filter(url_type=url_type_filter.upper())

        urls = list(queryset)
        
        if not urls:
            self.stdout.write(self.style.WARNING("No URLs found matching the filters."))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Checking {len(urls)} URL(s) using Playwright...")
        )

        total = len(urls)
        deactivated = 0
        reactivated = 0
        still_active = 0
        errors = []

        # Use requests session instead of Playwright browser
        for idx, url_obj in enumerate(urls, 1):
            display = f"{url_obj.county.name} ({url_obj.state.abbreviation}) -> {url_obj.base_url}"
            self.stdout.write(f"[{idx}/{total}] Checking {display}...", ending=" ")

            is_accessible, debug_info = self._check_url_with_playwright(
                None, url_obj.base_url, timeout
            )

            if is_accessible:
                self.stdout.write(self.style.SUCCESS("✓ OK"))
                
                if not url_obj.is_active:
                    url_obj.is_active = True
                    url_obj.save(update_fields=["is_active"])
                    reactivated += 1
                    self.stdout.write(self.style.SUCCESS(f"  → Reactivated"))
                else:
                    still_active += 1
            else:
                self.stdout.write(self.style.ERROR("✗ FAILED"))
                self.stdout.write(self.style.WARNING(f"  Debug: {debug_info}"))
                
                if url_obj.is_active:
                    url_obj.is_active = False
                    url_obj.save(update_fields=["is_active"])
                    deactivated += 1
                    self.stdout.write(
                        self.style.WARNING(f"  → Marked as inactive")
                    )
                
                errors.append(display)

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.MIGRATE_HEADING("Summary:"))
        self.stdout.write(f"  Total checked: {total}")
        self.stdout.write(self.style.ERROR(f"  Deactivated: {deactivated}") if deactivated > 0 else f"  Deactivated: {deactivated}")
        self.stdout.write(
            self.style.SUCCESS(f"  Reactivated: {reactivated}")
            if reactivated > 0
            else f"  Reactivated: {reactivated}"
        )
        self.stdout.write(self.style.SUCCESS(f"  Still active: {still_active}"))

        if errors:
            self.stdout.write("\n" + self.style.ERROR("URLs that failed:"))
            for error in errors:
                self.stdout.write(f"  - {error}")

        self.stdout.write("=" * 70)

    def _check_url_with_playwright(self, browser, url: str, timeout: int) -> tuple:
        """
        Check if a URL is accessible using requests with proper headers.
        Tries both http and https protocols.
        Returns (True, debug_msg) if page loads successfully.
        Returns (False, debug_msg) if page fails to load or returns errors.
        """
        # Parse the URL to normalize it
        parsed = urlparse(url)
        debug_msg = "Unknown error"

        # Browser-like headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        # If no scheme, try https first, then http
        if not parsed.scheme:
            schemes_to_try = ["https", "http"]
        else:
            schemes_to_try = [parsed.scheme]

        # Create session with retry strategy
        session = requests.Session()
        retry = Retry(
            total=1,
            backoff_factor=0.1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        for scheme in schemes_to_try:
            try:
                # Construct the full URL
                if not parsed.scheme:
                    full_url = f"{scheme}://{url}"
                else:
                    full_url = url

                # Convert ms to seconds for requests timeout
                timeout_sec = max(timeout / 1000, 5)  # Minimum 5 seconds

                # Try HEAD first (faster)
                try:
                    response = session.head(
                        full_url,
                        headers=headers,
                        timeout=timeout_sec,
                        allow_redirects=True,
                        verify=True
                    )
                    
                    if 200 <= response.status_code < 400:
                        session.close()
                        return True, f"Status {response.status_code}"
                    elif response.status_code == 403:
                        debug_msg = "Forbidden (403)"
                        continue
                    else:
                        debug_msg = f"Status {response.status_code}"
                        continue
                except:
                    # HEAD failed, try GET
                    pass

                # Try GET if HEAD failed or wasn't implemented
                try:
                    response = session.get(
                        full_url,
                        headers=headers,
                        timeout=timeout_sec,
                        allow_redirects=True,
                        verify=True,
                        stream=True  # Don't download full content
                    )
                    
                    if 200 <= response.status_code < 400:
                        session.close()
                        return True, f"Status {response.status_code}"
                    elif response.status_code == 403:
                        debug_msg = "Forbidden (403)"
                        continue
                    else:
                        debug_msg = f"Status {response.status_code}"
                        continue
                except requests.exceptions.Timeout:
                    debug_msg = f"Timeout ({timeout_sec}s)"
                    continue
                except requests.exceptions.ConnectionError:
                    debug_msg = "Connection error"
                    continue
                except Exception as e:
                    debug_msg = f"{type(e).__name__}"
                    continue

            except Exception as e:
                debug_msg = f"{type(e).__name__}"
                continue

        session.close()
        # If all schemes failed
        return False, debug_msg
