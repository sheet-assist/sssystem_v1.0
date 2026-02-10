"""
Job Execution Service for Scraper

Handles scraper job execution, data collection, and Prospect integration.
"""

import re
import traceback
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from django.utils import timezone
from django.db import transaction

from apps.scraper.models import ScrapingJob, JobExecutionLog, JobError
from apps.prospects.models import Prospect
from apps.locations.models import County, State

from .error_handler import ErrorHandler


# ============================================================================
# SCRAPER CONFIGURATION
# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

LABEL_REGEX_MAP = {
    r"auction\s*type": "auction_type",
    r"case\s*#|case\s*number": "case_number",
    r"final\s*judgment": "judgment_amount",
    r"parcel\s*id": "parcel_id",
    r"property\s*address": "address",
    r"assessed\s*value": "assessed_value",
    r"plaintiff\s*max\s*bid": "plaintiff_bid",
}

# Ensure scraped_data directory exists
SCRAPED_DATA_DIR = "scraped_data"
if not os.path.exists(SCRAPED_DATA_DIR):
    os.makedirs(SCRAPED_DATA_DIR)


# ============================================================================
# SCRAPER SERVICE
# ============================================================================

class AuctionScraper:
    """Scrapes auction data from county foreclosure sites"""
    
    def __init__(self, base_url: str, state: str, county: str):
        """
        Initialize scraper.
        
        Args:
            base_url: County base URL (e.g., https://www.miamidade.realforeclose.com/)
            state: State code (e.g., 'FL')
            county: County name (e.g., 'Miami-Dade')
        """
        self.base_url = base_url
        self.state = state
        self.county = county
        self.rows_collected = 0
    
    def scrape_date(self, page, auction_date: str) -> List[Dict]:
        """
        Scrape auctions for a specific date.
        
        Args:
            page: Playwright page object
            auction_date: Date string in MM/DD/YYYY format
            
        Returns:
            List of auction records
        """
        url = (
            f"{self.base_url}/index.cfm"
            f"?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={auction_date}"
        )
        
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        try:
            page.wait_for_selector(".AUCTION_ITEM", timeout=20000)
        except:
            return []
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        auctions = soup.select(".AUCTION_ITEM")
        
        rows = []
        
        for auction_elem in auctions:
            record = self._parse_auction_element(auction_elem, auction_date, url)
            if record:
                rows.append(record)
        
        self.rows_collected += len(rows)
        return rows
    
    def _parse_auction_element(self, elem, auction_date: str, page_url: str) -> Optional[Dict]:
        """
        Parse a single auction element into a record.
        
        Args:
            elem: BeautifulSoup element
            auction_date: Date string
            page_url: URL of the page
            
        Returns:
            Dictionary with auction data
        """
        try:
            auction_id = elem.get("aid", "")
            
            start_time = ""
            status = ""
            
            status_elem = elem.select_one(".ASTAT_MSGB")
            if status_elem:
                status_text = status_elem.get_text(strip=True)
                if "Canceled" in status_text:
                    status = "Canceled"
                else:
                    start_time = status_text
            
            record = {
                "state": self.state,
                "county": self.county,
                "auction_date": auction_date,
                "auction_id": auction_id,
                "start_time": start_time,
                "auction_type": "",
                "case_number": "",
                "judgment_amount": "",
                "parcel_id": "",
                "address": "",
                "city_state_zip": "",
                "assessed_value": "",
                "plaintiff_bid": "",
                "status": status,
                "sale_price": "",
                "sold_to": "",
                "source_url": page_url,
            }
            
            # Parse auction details
            for row in elem.select(".AUCTION_DETAILS table.ad_tab tr"):
                tds = row.select("td")
                if len(tds) < 2:
                    continue
                
                raw_label = tds[0].get_text(" ", strip=True).lower()
                value = tds[1].get_text(" ", strip=True)
                
                if raw_label == "":
                    record["city_state_zip"] = value
                    continue
                
                for pattern, field in LABEL_REGEX_MAP.items():
                    if re.search(pattern, raw_label, re.IGNORECASE):
                        record[field] = value
                        break
            
            # Parse sold details if not canceled
            if status != "Canceled":
                record["status"] = "Sold"
                
                auction_stats = elem.select_one(".AUCTION_STATS")
                if auction_stats:
                    sold_amount_elem = auction_stats.select_one(".ASTAT_MSGD")
                    sold_to_elem = auction_stats.select_one(".ASTAT_MSG_SOLDTO_MSG")
                    
                    if sold_amount_elem:
                        record["sale_price"] = sold_amount_elem.get_text(strip=True)
                    if sold_to_elem:
                        record["sold_to"] = sold_to_elem.get_text(strip=True)
            
            return record
        
        except Exception:
            return None
    
    def scrape_date_range(self, start_date: date, end_date: date) -> List[Dict]:
        """
        Scrape auctions for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (exclusive)
            
        Returns:
            List of all auction records
        """
        all_rows = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                extra_http_headers={**HEADERS, "Referer": self.base_url}
            )
            
            current_date = start_date
            while current_date < end_date:
                date_str = current_date.strftime("%m/%d/%Y")
                rows = self.scrape_date(page, date_str)
                all_rows.extend(rows)
                
                current_date += timedelta(days=1)
            
            browser.close()
        
        return all_rows


# ============================================================================
# JOB EXECUTION SERVICE
# ============================================================================

class JobExecutionService:
    """Manages scraping job execution"""
    
    def __init__(self, job: ScrapingJob):
        """
        Initialize execution service.
        
        Args:
            job: ScrapingJob instance
        """
        self.job = job
        self.execution_log = None
        self.error_handler = ErrorHandler()
    
    def execute(self) -> Dict:
        """
        Execute the scraping job.
        
        Returns:
            Dictionary with execution results
        """
        try:
            self.job.status = 'running'
            self.job.save()
            
            # Create execution log
            self.execution_log = JobExecutionLog.objects.create(
                job=self.job,
                status='in_progress'
            )
            
            start_time = timezone.now()
            
            # Run the scraper
            scraper = AuctionScraper(
                base_url=self._get_base_url(),
                state=self.job.state,
                county=self.job.county
            )
            
            rows = scraper.scrape_date_range(
                self.job.start_date,
                self.job.end_date
            )
            
            # Save results
            self._save_scraping_results(rows)
            
            # Update execution log
            end_time = timezone.now()
            self.execution_log.status = 'completed'
            self.execution_log.completed_at = end_time
            self.execution_log.execution_duration = end_time - start_time
            self.execution_log.rows_processed = len(rows)
            self.execution_log.save()
            
            # Update job
            self.job.status = 'completed'
            self.job.rows_processed = len(rows)
            self.job.rows_success = len(rows)
            self.job.save()
            
            return {
                'success': True,
                'rows_collected': len(rows),
                'duration': self.execution_log.execution_duration,
            }
        
        except Exception as e:
            return self._handle_execution_error(e)
    
    def _get_base_url(self) -> str:
        """Get the base URL for the county, trying each url_type."""
        from apps.scraper.models import CountyScrapeURL

        try:
            # Try to find an active URL for this county (any url_type)
            url_obj = CountyScrapeURL.objects.filter(
                county__name=self.job.county,
                county__state__abbreviation=self.job.state,
                is_active=True,
            ).first()
            if url_obj:
                return url_obj.base_url
        except Exception:
            pass

        # Fallback URL format
        county_slug = self.job.county.lower().replace(' ', '')
        return f"https://www.{county_slug}.realforeclose.com/"
    
    def _save_scraping_results(self, rows: List[Dict]):
        """
        Save scraping results to CSV and database.
        
        Args:
            rows: List of auction records
        """
        if not rows:
            return
        
        # Save to CSV
        csv_filename = f"{SCRAPED_DATA_DIR}/{self.job.state}_{self.job.county}_{self.job.id}.csv"
        df = pd.DataFrame(rows)
        df.to_csv(csv_filename, index=False)
        
        # Save to Prospects
        self._save_to_prospects(rows)
    
    def _save_to_prospects(self, rows: List[Dict]):
        """
        Convert and save auction records to Prospect model.
        
        Args:
            rows: List of auction records
        """
        converter = ProspectConverter(self.job)
        
        for row in rows:
            try:
                prospect_data = converter.convert_auction_to_prospect(row)
                if prospect_data:
                    Prospect.objects.get_or_create(**prospect_data)[0]
            except Exception as e:
                self.error_handler.log_error(
                    self.job,
                    e,
                    self.execution_log,
                    retry_attempt=0,
                )
    
    def _handle_execution_error(self, exception: Exception) -> Dict:
        """
        Handle execution errors.
        
        Args:
            exception: The exception that occurred
            
        Returns:
            Error result dictionary
        """
        self.error_handler.log_error(
            self.job,
            exception,
            self.execution_log,
            retry_attempt=0,
        )
        
        if self.execution_log:
            self.execution_log.status = 'failed'
            self.execution_log.completed_at = timezone.now()
            self.execution_log.save()
        
        self.job.status = 'failed'
        self.job.save()
        
        return {
            'success': False,
            'error': str(exception),
            'error_type': self.error_handler.categorize_error(exception),
        }


# ============================================================================
# PROSPECT CONVERTER
# ============================================================================

class ProspectConverter:
    """Converts auction data to Prospect model instances"""
    
    def __init__(self, job: ScrapingJob):
        """
        Initialize converter.
        
        Args:
            job: ScrapingJob instance
        """
        self.job = job
        self.county_obj = self._get_county_object()
    
    def _get_county_object(self) -> Optional[County]:
        """Get County object from job"""
        try:
            return County.objects.get(
                name=self.job.county,
                state__abbreviation=self.job.state
            )
        except:
            return None
    
    def convert_auction_to_prospect(self, auction_record: Dict) -> Optional[Dict]:
        """
        Convert an auction record to Prospect data.
        
        Args:
            auction_record: Dictionary with auction data
            
        Returns:
            Dictionary with Prospect model fields, or None if invalid
        """
        try:
            # Parse and clean auction data
            address = auction_record.get('address', '').strip()
            case_number = auction_record.get('case_number', '').strip() or f"AUTO_{auction_record.get('auction_id', '')}"
            auction_date = self._parse_date(auction_record.get('auction_date'))
            
            prospect_data = {
                'prospect_type': 'SS',  # Sheriff Sale by default
                'case_number': case_number,
                'county': self.county_obj,
                'property_address': address,
                'auction_date': auction_date,
                'auction_status': self._normalize_status(auction_record.get('status', 'scheduled')),
                'auction_type': auction_record.get('auction_type', ''),
                'final_judgment_amount': self._parse_currency(auction_record.get('judgment_amount')),
                'plaintiff_max_bid': self._parse_currency(auction_record.get('plaintiff_bid')),
                'assessed_value': self._parse_currency(auction_record.get('assessed_value')),
                'sale_amount': self._parse_currency(auction_record.get('sale_price')),
                'sold_to': auction_record.get('sold_to', ''),
                'parcel_id': auction_record.get('parcel_id', ''),
                'source_url': auction_record.get('source_url', ''),
                'raw_data': auction_record,
            }
            
            # Validate required fields
            if not prospect_data['property_address'] or not prospect_data['county']:
                return None
            
            return prospect_data
        
        except Exception:
            return None
    
    def _normalize_status(self, status_str: str) -> str:
        """
        Normalize auction status string to Prospect model choice.
        
        Args:
            status_str: Status from auction scraper
            
        Returns:
            Valid Prospect auction_status choice
        """
        status_map = {
            'Sold': 'sold_third_party',
            'Canceled': 'cancelled',
            'Postponed': 'postponed',
            'Scheduled': 'scheduled',
        }
        
        for key, value in status_map.items():
            if key.lower() in status_str.lower():
                return value
        
        return 'scheduled'  # Default
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string (MM/DD/YYYY format)"""
        try:
            return datetime.strptime(date_str, '%m/%d/%Y').date()
        except:
            return None
    
    def _parse_currency(self, value: str) -> Optional[float]:
        """Parse currency string to float"""
        try:
            if not value:
                return None
            # Remove $, commas, spaces
            cleaned = re.sub(r'[$,\s]', '', value)
            return float(cleaned)
        except:
            return None
