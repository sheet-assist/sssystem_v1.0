"""
Playwright-based scraper engine for realforeclose.com / realtaxdeed.com.
Uses county URL fields directly — no hardcoded URL generation.
Mirrors scrape.py run_auctions() pattern: Playwright + BS4.
"""
import random
import time
import asyncio
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
    Get the base URL from CountyScrapeURL for the given county and job type.
    Falls back to legacy county fields if no CountyScrapeURL record exists.
    Raises ValueError if URL not configured anywhere.
    """
    from .models import CountyScrapeURL
    print(f"Getting base URL for {county} and job type {job_type}")
    # Try CountyScrapeURL first
    try:
        url_obj = CountyScrapeURL.objects.get(
            county=county,
            url_type=job_type,
            is_active=True,
        )
        return url_obj.base_url.rstrip("/")
    except CountyScrapeURL.DoesNotExist:
        pass

    # Fallback to legacy county fields
    if job_type == "TD":
        url = getattr(county, "taxdeed_url", None)
    else:
        url = getattr(county, "foreclosure_url", None)

    if not url:
        raise ValueError(
            f"No URL configured for county {county.name} "
            f"with job type {job_type}. Add it in County Scrape URLs admin."
        )
    return url.rstrip("/")


def build_auction_url(base_url, auction_date):
    """Build the full calendar URL for a date — same format as scrape.py."""
    date_str = auction_date.strftime("%m/%d/%Y")
    print(f"Building auction URL with base {base_url} and date {date_str}")
    return f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date_str}"


def scrape_single_date(page, base_url, auction_date, log_fn):
    """
    Scrape auctions for a single date using an existing Playwright page.
    Mirrors scrape.py rundates() logic exactly — inline parsing with BeautifulSoup.
    Returns list of raw auction dicts from the parser.
    """
    from bs4 import BeautifulSoup
    import re
    from decimal import Decimal
    
    # Regex patterns for label extraction
    LABEL_REGEX_MAP = {
        r"auction\s*type": "auction_type",
        r"case\s*#|case\s*number": "case_number",
        r"final\s*judgment": "final_judgment_amount",
        r"parcel\s*id": "parcel_id",
        r"property\s*address": "property_address",
        r"assessed\s*value": "assessed_value",
        r"plaintiff\s*max\s*bid": "plaintiff_max_bid",
    }
    
    url = build_auction_url(base_url, auction_date)
    print(f"Navigating to {url}")
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print("Page loaded, waiting for auction items...")
    except Exception as e:
        print(f"Failed to navigate to {url}: {e}")
        log_fn("warning", f"Failed to navigate to {url}: {e}")
        return [], url
    
    time.sleep(random.uniform(1, 2))
    
    try:
        page.wait_for_selector(".AUCTION_ITEM", timeout=10000)
    except Exception as e:
        print(f"No auctions found for {auction_date}")
        log_fn("warning", f"No auctions found for {auction_date}")
        return [], url
    
    # Parse page with BeautifulSoup — inline like scrape.py
    try:
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        raw_auctions = []
        
        for item in soup.select(".AUCTION_ITEM"):
            auction_id = item.get("aid", "")
            
            # Start time / status from .ASTAT_MSGB
            status_elem = item.select_one(".ASTAT_MSGB")
            start_time = status_elem.get_text(strip=True) if status_elem else ""
            
            # Determine auction status
            auction_status = ""
            if start_time and ("Canceled" in start_time or "Cancelled" in start_time):
                auction_status = "cancelled"
                start_time = ""
            elif start_time and "Postponed" in start_time:
                auction_status = "postponed"
                start_time = ""
            
            record = {
                "auction_id": auction_id,
                "start_time": start_time,
                "auction_type": "",
                "case_number": "",
                "final_judgment_amount": None,
                "parcel_id": "",
                "property_address": "",
                "city_state_zip": "",
                "assessed_value": None,
                "plaintiff_max_bid": None,
                "auction_status": auction_status,
                "sold_amount": None,
                "sold_to": "",
            }
            
            # Extract auction details from table
            for row in item.select(".AUCTION_DETAILS table.ad_tab tr"):
                tds = row.select("td")
                if len(tds) < 2:
                    continue
                
                raw_label = tds[0].get_text(" ", strip=True).lower()
                value = tds[1].get_text(" ", strip=True)
                
                # Empty label = City/State/Zip
                if raw_label == "":
                    record["city_state_zip"] = value
                    continue
                
                # Match label with regex patterns
                for pattern, field_name in LABEL_REGEX_MAP.items():
                    if re.search(pattern, raw_label, re.IGNORECASE):
                        record[field_name] = value
                        break
            
            # Extract sold details
            auction_stats = item.select_one(".AUCTION_STATS")
            if auction_status == "":
                record["auction_status"] = "sold"
                
                if auction_stats:
                    sold_amount = auction_stats.select_one(".ASTAT_MSGD")
                    sold_to = auction_stats.select_one(".ASTAT_MSG_SOLDTO_MSG")
                    
                    if sold_amount:
                        record["sold_amount"] = sold_amount.get_text(strip=True)
                    if sold_to:
                        record["sold_to"] = sold_to.get_text(strip=True)
            
            raw_auctions.append(record)
        
        print(f"Parsed {len(raw_auctions)} auctions from {auction_date}")
        # log_fn("info", f"Found {len(raw_auctions)} auctions for {auction_date}")
        return raw_auctions, url
        
    except Exception as e:
        print(f"Error parsing page content: {e}")
        # log_fn("error", f"Error parsing page content: {e}")
        return [], url


def run_scrape_job(job):
    """
    Execute a ScrapeJob: iterate dates, scrape, create/update Prospects, qualify.
    Uses a single Playwright browser session across all dates (like scrape.py run_auctions).
    """
    # Clear any existing event loop to prevent async context issues with Django ORM
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to be more careful
            pass
        else:
            asyncio.set_event_loop(None)
    except RuntimeError:
        # No event loop exists, which is good
        pass
    
    # Now run the actual scraping with fresh context
    _run_scrape_job_impl(job)


def _run_scrape_job_impl(job):
    """
    Implementation of scrape job execution.
    Separated to ensure event loop context is cleared before this runs.
    """
    from playwright.sync_api import sync_playwright

    from apps.prospects.models import Prospect
    from apps.settings_app.evaluation import evaluate_prospect
    print(f"Starting scrape job {job.pk} for {job.county} {job.job_type} on {job.target_date}")
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
        print(f"Using base URL: {base_url}")
        # Build date range
        start_date = job.target_date
        end_date = job.end_date or job.target_date
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

        # Collect all scraped data FIRST, before any Django ORM operations
        all_scraped_data = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                extra_http_headers={**HEADERS, "Referer": base_url}
            )

            try:
                for d in dates:
                    print(f"Scraping for date: {d}")
                    raw_auctions, source_url = scrape_single_date(page, base_url, d, log_fn)
                    print("getting results...")
                    print(source_url, len(raw_auctions))
                    
                    # Collect raw auction data without doing ORM operations
                    for raw in raw_auctions:
                        try:
                            print(f"Processing auction {raw.get('auction_id')} with case number {raw.get('case_number')}")
                            data = normalize_prospect_data(raw, d, job.job_type, source_url)
                            case_number = data["case_number"]
                            print(case_number)
                            if case_number:
                                all_scraped_data.append({
                                    'data': data,
                                    'date': d,
                                    'case_number': case_number,
                                })
                        except Exception as e:
                            print(f"Error processing auction: {e}")

            finally:
                browser.close()

        # NOW process all collected data with Django ORM (outside Playwright context)
        created = 0
        updated = 0
        qualified_count = 0
        disqualified_count = 0
        
        for item in all_scraped_data:
            try:
                data = item['data']
                d = item['date']
                case_number = item['case_number']
                
                # Ensure all required fields exist in data with defaults
                defaults = {
                    "prospect_type": data.get("prospect_type", ""),
                    "auction_item_number": data.get("auction_item_number", ""),
                    "auction_type": data.get("auction_type", ""),
                    "property_address": data.get("property_address", ""),
                    "city": data.get("city", ""),
                    "state": data.get("state", ""),
                    "zip_code": data.get("zip_code", ""),
                    "parcel_id": data.get("parcel_id", ""),
                    "final_judgment_amount": data.get("final_judgment_amount"),
                    "plaintiff_max_bid": data.get("plaintiff_max_bid"),
                    "assessed_value": data.get("assessed_value"),
                    "sale_amount": data.get("sale_amount"),
                    "sold_to": data.get("sold_to", ""),
                    "auction_status": data.get("auction_status", ""),
                    "source_url": data.get("source_url", ""),
                    "raw_data": data.get("raw_data", {}),
                }
                
                prospect, is_new = Prospect.objects.get_or_create(
                    county=county,
                    case_number=case_number,
                    auction_date=d,
                    defaults=defaults,
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
                    prospect.raw_data = data.get("raw_data", {})
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
                print(f"Error saving prospect: {e}")
                print(f"Data keys available: {list(data.keys()) if 'data' in locals() else 'N/A'}")
                log_fn("error", f"Failed to save prospect {case_number if 'case_number' in locals() else 'unknown'}: {e}")

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
