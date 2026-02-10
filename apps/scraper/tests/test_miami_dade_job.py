"""
Integration test: Create a Miami-Dade FL job for Feb 2 2025,
scrape the data, and verify the job status is updated through
the full lifecycle (pending → running → completed).
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.locations.models import County, State
from apps.scraper.models import (
    CountyScrapeURL, JobExecutionLog, JobError, ScrapingJob,
)
from apps.scraper.services.job_service import (
    AuctionScraper, JobExecutionService,
)

User = get_user_model()

# Sample auction rows that the scraper would return for Miami-Dade
MOCK_AUCTION_ROWS = [
    {
        "state": "FL",
        "county": "Miami-Dade",
        "auction_date": "02/02/2025",
        "auction_id": "90001",
        "start_time": "09:00 AM",
        "auction_type": "FORECLOSURE",
        "case_number": "2025-000111",
        "judgment_amount": "$185,000.00",
        "parcel_id": "30-2109-001-0010",
        "address": "1450 NW 3rd St",
        "city_state_zip": "Miami, FL 33125",
        "assessed_value": "$210,000.00",
        "plaintiff_bid": "$190,000.00",
        "status": "Sold",
        "sale_price": "$195,500.00",
        "sold_to": "Third Party",
        "source_url": "https://www.miamidade.realforeclose.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=02/02/2025",
    },
    {
        "state": "FL",
        "county": "Miami-Dade",
        "auction_date": "02/02/2025",
        "auction_id": "90002",
        "start_time": "09:30 AM",
        "auction_type": "FORECLOSURE",
        "case_number": "2025-000222",
        "judgment_amount": "$320,000.00",
        "parcel_id": "30-3108-002-0020",
        "address": "8825 SW 124th Ave",
        "city_state_zip": "Miami, FL 33186",
        "assessed_value": "$350,000.00",
        "plaintiff_bid": "$325,000.00",
        "status": "Canceled",
        "sale_price": "",
        "sold_to": "",
        "source_url": "https://www.miamidade.realforeclose.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=02/02/2025",
    },
    {
        "state": "FL",
        "county": "Miami-Dade",
        "auction_date": "02/02/2025",
        "auction_id": "90003",
        "start_time": "10:00 AM",
        "auction_type": "FORECLOSURE",
        "case_number": "2025-000333",
        "judgment_amount": "$92,500.00",
        "parcel_id": "30-4107-003-0030",
        "address": "255 NE 79th St",
        "city_state_zip": "Miami, FL 33138",
        "assessed_value": "$115,000.00",
        "plaintiff_bid": "$95,000.00",
        "status": "Sold",
        "sale_price": "$98,000.00",
        "sold_to": "Plaintiff",
        "source_url": "https://www.miamidade.realforeclose.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=02/02/2025",
    },
]


class MiamiDadeJobIntegrationTest(TestCase):
    """
    End-to-end: create job → execute scrape → verify status updates.
    The actual HTTP/Playwright call is mocked; everything else runs for real.
    """

    def setUp(self):
        self.state = State.objects.create(
            name="Florida", abbreviation="FL", is_active=True,
        )
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            is_active=True,
        )
        CountyScrapeURL.objects.create(
            county=self.county,
            state=self.state,
            url_type="MF",
            base_url="https://www.miamidade.realforeclose.com/",
        )
        self.admin = User.objects.create_superuser(
            username="admin", password="pass",
        )

    # ------------------------------------------------------------------
    # 1. CREATE JOB
    # ------------------------------------------------------------------
    def _create_job(self) -> ScrapingJob:
        job = ScrapingJob.objects.create(
            name="Miami-Dade Auctions Feb 2 2025",
            state="FL",
            county="Miami-Dade",
            start_date=date(2025, 2, 2),
            end_date=date(2025, 2, 3),   # end_date is exclusive in scraper
            created_by=self.admin,
        )
        return job

    # ------------------------------------------------------------------
    # FULL LIFECYCLE: pending → running → completed
    # ------------------------------------------------------------------
    @patch.object(AuctionScraper, "scrape_date_range", return_value=MOCK_AUCTION_ROWS)
    def test_full_job_lifecycle(self, mock_scrape):
        """Create → execute → verify completed status and row counts."""

        # --- Step 1: Create the job ---
        job = self._create_job()
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.state, "FL")
        self.assertEqual(job.county, "Miami-Dade")
        self.assertEqual(job.start_date, date(2025, 2, 2))
        self.assertEqual(job.rows_processed, 0)

        # --- Step 2: Execute the job (scrape) ---
        service = JobExecutionService(job)
        result = service.execute()

        # --- Step 3: Verify status updated to completed ---
        job.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.rows_processed, 3)
        self.assertEqual(job.rows_success, 3)

        # --- Step 4: Verify execution log created ---
        logs = JobExecutionLog.objects.filter(job=job)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.status, "completed")
        self.assertEqual(log.rows_processed, 3)
        self.assertIsNotNone(log.completed_at)
        self.assertIsNotNone(log.execution_duration)

        # --- Step 5: No errors logged ---
        self.assertEqual(JobError.objects.filter(job=job).count(), 0)

    # ------------------------------------------------------------------
    # FAILURE SCENARIO: pending → running → failed
    # ------------------------------------------------------------------
    @patch.object(
        AuctionScraper, "scrape_date_range",
        side_effect=ConnectionError("Could not reach miamidade.realforeclose.com"),
    )
    def test_job_failure_sets_failed_and_logs_error(self, mock_scrape):
        """When the scraper fails, job goes to 'failed' and error is logged."""

        job = self._create_job()
        self.assertEqual(job.status, "pending")

        service = JobExecutionService(job)
        result = service.execute()

        job.refresh_from_db()
        self.assertFalse(result["success"])
        self.assertEqual(job.status, "failed")
        self.assertEqual(result["error_type"], "Network")

        # Execution log marked as failed
        log = JobExecutionLog.objects.filter(job=job).first()
        self.assertEqual(log.status, "failed")

        # Error record created
        errors = JobError.objects.filter(job=job)
        self.assertEqual(errors.count(), 1)
        error = errors.first()
        self.assertEqual(error.error_type, "Network")
        self.assertTrue(error.is_retryable)
        self.assertIn("miamidade", error.error_message)

    # ------------------------------------------------------------------
    # EMPTY RESULTS SCENARIO
    # ------------------------------------------------------------------
    @patch.object(AuctionScraper, "scrape_date_range", return_value=[])
    def test_job_completes_with_zero_rows(self, mock_scrape):
        """Job completes successfully even if no auctions found for the date."""

        job = self._create_job()
        service = JobExecutionService(job)
        result = service.execute()

        job.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.rows_processed, 0)
        self.assertEqual(job.rows_success, 0)

    # ------------------------------------------------------------------
    # VERIFY CORRECT URL USED
    # ------------------------------------------------------------------
    @patch.object(AuctionScraper, "scrape_date_range", return_value=[])
    def test_scraper_uses_county_base_url(self, mock_scrape):
        """Verify the service resolves the correct base URL for Miami-Dade."""

        job = self._create_job()
        service = JobExecutionService(job)
        url = service._get_base_url()
        self.assertEqual(url, "https://www.miamidade.realforeclose.com/")
