"""
Playwright-based scraper engine for realforeclose.com / realtaxdeed.com.
Uses county URL fields directly — no hardcoded URL generation.
Mirrors scrape.py run_auctions() pattern: Playwright + BS4.
"""
import random
import time
from datetime import timedelta

from django.utils import timezone

from .models import ScrapeJob, ScrapeLog
from .parsers import normalize_prospect_data, parse_calendar_page


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def get_base_url(county, job_type):
    """
    Get the base URL from county fields. No fallback generation.
    Raises ValueError if URL not configured.
    """
    if job_type == "TD":
        url = county.taxdeed_url
    else:
        url = county.foreclosure_url

    if not url:
        raise ValueError(
            f"No {'taxdeed_url' if job_type == 'TD' else 'foreclosure_url'} "
            f"configured for county {county.name}. Set it in County admin."
        )
    return url.rstrip("/")


def build_auction_url(base_url, auction_date):
    """Build the full calendar URL for a date — same format as scrape.py."""
    date_str = auction_date.strftime("%m/%d/%Y")
    return f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date_str}"


def scrape_single_date(page, base_url, auction_date, log_fn):
    """
    Scrape auctions for a single date using an existing Playwright page.
    Mirrors scrape.py rundates() logic.
    Returns list of raw auction dicts from the parser.
    """
    url = build_auction_url(base_url, auction_date)
    log_fn("info", f"Navigating to {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(1, 2))

    try:
        page.wait_for_selector(".AUCTION_ITEM", timeout=20000)
    except Exception:
        log_fn("warning", f"No auctions found for {auction_date}")
        return [], url

    html = page.content()
    raw_auctions = parse_calendar_page(html)
    log_fn("info", f"Found {len(raw_auctions)} auctions for {auction_date}")
    return raw_auctions, url


def run_scrape_job(job):
    """
    Execute a ScrapeJob: iterate dates, scrape, create/update Prospects, qualify.
    Uses a single Playwright browser session across all dates (like scrape.py run_auctions).
    """
    from playwright.sync_api import sync_playwright

    from apps.prospects.models import Prospect
    from apps.settings_app.evaluation import evaluate_prospect

    job.status = "running"
    job.started_at = timezone.now()
    job.save()

    def log_fn(level, message, raw_html=""):
        ScrapeLog.objects.create(
            job=job, level=level, message=message,
            raw_html=raw_html[:5000] if raw_html else "",
        )

    try:
        county = job.county
        base_url = get_base_url(county, job.job_type)

        # Build date range
        start_date = job.target_date
        end_date = job.end_date or job.target_date
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

        created = 0
        updated = 0
        qualified_count = 0
        disqualified_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                extra_http_headers={**HEADERS, "Referer": base_url}
            )

            try:
                for d in dates:
                    raw_auctions, source_url = scrape_single_date(page, base_url, d, log_fn)

                    for raw in raw_auctions:
                        try:
                            data = normalize_prospect_data(raw, d, job.job_type, source_url)
                            case_number = data["case_number"]
                            if not case_number:
                                log_fn("warning", f"Skipped auction with no case number: {raw.get('auction_id')}")
                                continue

                            prospect, is_new = Prospect.objects.get_or_create(
                                county=county,
                                case_number=case_number,
                                auction_date=d,
                                defaults={
                                    "prospect_type": data["prospect_type"],
                                    "auction_item_number": data["auction_item_number"],
                                    "auction_type": data["auction_type"],
                                    "property_address": data["property_address"],
                                    "city": data["city"],
                                    "state": data["state"],
                                    "zip_code": data["zip_code"],
                                    "parcel_id": data["parcel_id"],
                                    "final_judgment_amount": data["final_judgment_amount"],
                                    "plaintiff_max_bid": data["plaintiff_max_bid"],
                                    "assessed_value": data["assessed_value"],
                                    "sale_amount": data["sale_amount"],
                                    "sold_to": data["sold_to"],
                                    "auction_status": data["auction_status"],
                                    "source_url": data["source_url"],
                                    "raw_data": data["raw_data"],
                                },
                            )

                            if is_new:
                                created += 1
                            else:
                                # Update mutable fields on existing prospects
                                for field in (
                                    "auction_status", "sale_amount", "sold_to",
                                    "property_address", "city", "state", "zip_code",
                                    "assessed_value", "final_judgment_amount",
                                    "plaintiff_max_bid", "auction_type",
                                ):
                                    val = data.get(field)
                                    if val not in (None, ""):
                                        setattr(prospect, field, val)
                                prospect.raw_data = data["raw_data"]
                                prospect.save()
                                updated += 1

                            # Evaluate qualification
                            is_qualified, reasons = evaluate_prospect(data, county)
                            prospect.qualification_status = "qualified" if is_qualified else "disqualified"
                            prospect.save(update_fields=["qualification_status"])

                            if is_qualified:
                                qualified_count += 1
                            else:
                                disqualified_count += 1

                        except Exception as e:
                            log_fn("error", f"Failed to save prospect {raw.get('case_number')}: {e}")

            finally:
                browser.close()

        # Update job results
        job.status = "completed"
        job.prospects_created = created
        job.prospects_updated = updated
        job.prospects_qualified = qualified_count
        job.prospects_disqualified = disqualified_count
        job.completed_at = timezone.now()
        job.save()

        county.update_last_scraped()
        log_fn("info", f"Completed: {created} created, {updated} updated, {qualified_count} qualified")

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = timezone.now()
        job.save()
        log_fn("error", f"Job failed: {e}")
        raise
