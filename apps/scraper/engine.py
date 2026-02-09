"""
Playwright-based scraper for realforeclose.com and realtaxdeed.com.
Handles headless browser automation, pagination, and data extraction.
"""
import random
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from .parsers import parse_calendar_page, normalize_prospect_data
from .models import ScrapeJob, ScrapeLog


class RealtdmScraper:
    """Scrapes realforeclose.com or realtaxdeed.com for auction listings."""
    
    def __init__(self, job):
        self.job = job
        self.base_url = self.get_base_url()
    
    def get_base_url(self):
        """Get base URL for county from county config."""
        county_config = self.job.county
        # Use taxdeed_url if available, else realforeclose_url
        if self.job.job_type == 'TD':
            return county_config.taxdeed_url or f"https://{county_config.slug}.realtaxdeed.com"
        else:
            return county_config.foreclosure_url or f"https://{county_config.slug}.realforeclose.com"
    
    def log(self, level, message, raw_html=''):
        """Create a ScrapeLog entry."""
        ScrapeLog.objects.create(
            job=self.job,
            level=level,
            message=message,
            raw_html=raw_html[:5000] if raw_html else ''  # Truncate HTML
        )
    
    def random_delay(self, min_sec=1, max_sec=3):
        """Random delay to avoid rate limiting."""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def scrape_date(self, auction_date):
        """
        Scrape auctions for a single date.
        Returns list of normalized prospect dicts.
        """
        prospects = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            try:
                # Navigate to calendar URL
                url = self._build_calendar_url(auction_date)
                self.log('info', f'Navigating to {url}')
                
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                self.random_delay(1, 2)
                
                # Wait for auctions to load
                try:
                    page.wait_for_selector('.AUCTION_ITEM', timeout=20000)
                except:
                    self.log('warning', f'No auctions found for {auction_date}')
                    return prospects
                
                # Get page content and parse
                html = page.content()
                raw_auctions = parse_calendar_page(html, self.job.county.slug)
                
                self.log('info', f'Found {len(raw_auctions)} auctions')
                
                # Normalize each auction
                for raw in raw_auctions:
                    try:
                        prospect = normalize_prospect_data(raw, auction_date, self.job.job_type)
                        prospects.append(prospect)
                    except Exception as e:
                        self.log('error', f'Failed to normalize auction {raw.get("auction_id")}: {str(e)}')
                
                # Check for pagination
                prospects.extend(self._scrape_pages(page, auction_date))
                
            except Exception as e:
                self.log('error', f'Scrape failed for {auction_date}: {str(e)}', page.content())
                raise
            finally:
                browser.close()
        
        return prospects
    
    def _build_calendar_url(self, auction_date):
        """Build calendar page URL for a date."""
        date_str = auction_date.strftime('%m/%d/%Y')
        return f"{self.base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date_str}"
    
    def _scrape_pages(self, page, auction_date):
        """Handle pagination if present."""
        prospects = []
        # Implement pagination logic if needed
        return prospects


def run_scrape_job(job):
    """
    Execute a scrape job: download, parse, create/update prospects, qualify, log results.
    """
    from apps.settings_app.utils import evaluate_prospect
    from apps.prospects.models import Prospect
    from apps.locations.models import County
    from django.utils import timezone
    
    job.status = 'running'
    job.started_at = timezone.now()
    job.save()
    
    try:
        scraper = RealtdmScraper(job)
        prospects_data = scraper.scrape_date(job.target_date)
        
        created = 0
        updated = 0
        qualified = 0
        disqualified = 0
        
        for prospect_data in prospects_data:
            try:
                county = job.county
                
                # Try to get existing prospect
                prospect_obj, is_new = Prospect.objects.get_or_create(
                    county=county,
                    case_number=prospect_data['case_number'],
                    auction_date=prospect_data['auction_date'],
                    defaults={
                        'prospect_type': prospect_data['prospect_type'],
                        'auction_item_number': prospect_data['auction_item_number'],
                        'property_address': prospect_data['property_address'],
                        'parcel_id': prospect_data['parcel_id'],
                        'final_judgment_amount': prospect_data['final_judgment_amount'],
                        'plaintiff_max_bid': prospect_data['plaintiff_max_bid'],
                        'assessed_value': prospect_data['assessed_value'],
                        'auction_status': prospect_data['auction_status'],
                        'raw_data': prospect_data['raw_data'],
                    }
                )
                
                if is_new:
                    created += 1
                else:
                    updated += 1
                
                # Evaluate qualification
                qualification_result = evaluate_prospect(prospect_data, county)
                if qualification_result:
                    prospect_obj.qualification_status = 'qualified'
                    qualified += 1
                else:
                    prospect_obj.qualification_status = 'disqualified'
                    disqualified += 1
                
                prospect_obj.save()
                
            except Exception as e:
                scraper.log('error', f'Failed to save prospect {prospect_data.get("case_number")}: {str(e)}')
        
        # Update job results
        job.status = 'completed'
        job.prospects_created = created
        job.prospects_updated = updated
        job.prospects_qualified = qualified
        job.prospects_disqualified = disqualified
        job.completed_at = timezone.now()
        job.save()
        
        scraper.log('info', f'Scrape completed: {created} created, {updated} updated, {qualified} qualified')
        
    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = timezone.now()
        job.save()
        
        scraper.log('error', f'Scrape job failed: {str(e)}')
        raise
