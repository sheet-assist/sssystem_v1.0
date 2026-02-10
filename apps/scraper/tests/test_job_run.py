"""
Tests for Job Execution - async execution, JobExecutionService, and API endpoints.
"""
import json
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.locations.models import County, State
from apps.scraper.models import (
    CountyScrapeURL, JobError, JobExecutionLog, ScrapingJob,
)
from apps.scraper.services.async_tasks import (
    JobBatchProcessor, JobExecutor, JobRetryManager,
    execute_job_async, get_job_status_polling, retry_failed_job,
)
from apps.scraper.services.job_service import (
    AuctionScraper, JobExecutionService, ProspectConverter,
)

User = get_user_model()


# ============================================================================
# JOB EXECUTION SERVICE TESTS
# ============================================================================

class JobExecutionServiceTest(TestCase):
    """Test JobExecutionService.execute() workflow."""

    def setUp(self):
        self.state = State.objects.create(
            name="Florida", abbreviation="FL", is_active=True
        )
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade", is_active=True,
        )
        self.scrape_url = CountyScrapeURL.objects.create(
            county=self.county,
            state=self.state,
            url_type="MF",
            base_url="https://www.miamidade.realforeclose.com/",
        )
        self.user = User.objects.create_superuser(username="admin", password="pass")
        self.job = ScrapingJob.objects.create(
            name="Exec Test",
            state="FL",
            county="Miami-Dade",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
            created_by=self.user,
        )

    @patch.object(AuctionScraper, "scrape_date_range")
    def test_execute_success_updates_job_completed(self, mock_scrape):
        mock_scrape.return_value = [
            {"auction_id": "1", "address": "123 Main St", "case_number": "C-001",
             "auction_date": "03/01/2026", "status": "Sold", "sale_price": "$50,000",
             "county": "Miami-Dade", "state": "FL"},
        ]
        service = JobExecutionService(self.job)
        result = service.execute()

        self.job.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.rows_processed, 1)

    @patch.object(AuctionScraper, "scrape_date_range")
    def test_execute_creates_execution_log(self, mock_scrape):
        mock_scrape.return_value = []
        service = JobExecutionService(self.job)
        service.execute()

        logs = JobExecutionLog.objects.filter(job=self.job)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().status, "completed")

    @patch.object(AuctionScraper, "scrape_date_range")
    def test_execute_sets_status_running_then_completed(self, mock_scrape):
        statuses_seen = []

        original_save = self.job.save

        def tracking_save(*args, **kwargs):
            statuses_seen.append(self.job.status)
            original_save(*args, **kwargs)

        mock_scrape.return_value = []
        with patch.object(ScrapingJob, "save", side_effect=tracking_save):
            service = JobExecutionService(self.job)
            service.execute()

        self.assertIn("running", statuses_seen)
        self.assertIn("completed", statuses_seen)

    @patch.object(AuctionScraper, "scrape_date_range", side_effect=ConnectionError("Network down"))
    def test_execute_failure_sets_status_failed(self, mock_scrape):
        service = JobExecutionService(self.job)
        result = service.execute()

        self.job.refresh_from_db()
        self.assertFalse(result["success"])
        self.assertEqual(self.job.status, "failed")
        self.assertIn("Network down", result["error"])

    @patch.object(AuctionScraper, "scrape_date_range", side_effect=TimeoutError("Timed out"))
    def test_execute_failure_creates_error_record(self, mock_scrape):
        service = JobExecutionService(self.job)
        service.execute()

        errors = JobError.objects.filter(job=self.job)
        self.assertEqual(errors.count(), 1)
        self.assertEqual(errors.first().error_type, "Network")
        self.assertIn("Timed out", errors.first().error_message)

    @patch.object(AuctionScraper, "scrape_date_range", side_effect=Exception("Unexpected"))
    def test_execute_failure_marks_execution_log_failed(self, mock_scrape):
        service = JobExecutionService(self.job)
        service.execute()

        log = JobExecutionLog.objects.filter(job=self.job).first()
        self.assertEqual(log.status, "failed")
        self.assertIsNotNone(log.completed_at)

    @patch.object(AuctionScraper, "scrape_date_range")
    def test_execute_records_duration(self, mock_scrape):
        mock_scrape.return_value = []
        service = JobExecutionService(self.job)
        service.execute()

        log = JobExecutionLog.objects.filter(job=self.job).first()
        self.assertIsNotNone(log.execution_duration)

    def test_get_base_url_from_county_scrape_url(self):
        service = JobExecutionService(self.job)
        url = service._get_base_url()
        self.assertEqual(url, "https://www.miamidade.realforeclose.com/")

    def test_get_base_url_fallback_when_no_record(self):
        self.scrape_url.delete()
        service = JobExecutionService(self.job)
        url = service._get_base_url()
        self.assertIn("realforeclose.com", url)


# ============================================================================
# AUCTION SCRAPER UNIT TESTS
# ============================================================================

class AuctionScraperTest(TestCase):
    """Test AuctionScraper parsing and configuration."""

    def test_init_sets_fields(self):
        scraper = AuctionScraper(
            base_url="https://example.com",
            state="FL",
            county="Test",
        )
        self.assertEqual(scraper.base_url, "https://example.com")
        self.assertEqual(scraper.state, "FL")
        self.assertEqual(scraper.county, "Test")
        self.assertEqual(scraper.rows_collected, 0)

    def test_parse_auction_element_returns_none_on_bad_html(self):
        scraper = AuctionScraper("https://example.com", "FL", "Test")
        from bs4 import BeautifulSoup
        bad_elem = BeautifulSoup("<div></div>", "html.parser").div
        result = scraper._parse_auction_element(bad_elem, "01/01/2026", "https://example.com")
        # Should return a dict (with empty fields) or None gracefully
        # The method handles exceptions internally
        self.assertTrue(result is None or isinstance(result, dict))


# ============================================================================
# PROSPECT CONVERTER TESTS
# ============================================================================

class ProspectConverterTest(TestCase):
    """Test ProspectConverter data transformation."""

    def setUp(self):
        self.state = State.objects.create(
            name="Florida", abbreviation="FL", is_active=True
        )
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade", is_active=True,
        )
        self.job = ScrapingJob.objects.create(
            name="Converter Test",
            state="FL",
            county="Miami-Dade",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
        )

    def test_convert_valid_auction_record(self):
        converter = ProspectConverter(self.job)
        record = {
            "auction_id": "123",
            "address": "100 Main St",
            "case_number": "C-001",
            "auction_date": "03/01/2026",
            "status": "Sold",
            "judgment_amount": "$50,000.00",
            "plaintiff_bid": "$30,000.00",
            "assessed_value": "$80,000.00",
            "sale_price": "$55,000.00",
            "sold_to": "Third Party",
            "parcel_id": "001-001",
            "auction_type": "FORECLOSURE",
            "source_url": "https://example.com",
        }
        result = converter.convert_auction_to_prospect(record)
        self.assertIsNotNone(result)
        self.assertEqual(result["case_number"], "C-001")
        self.assertEqual(result["property_address"], "100 Main St")
        self.assertEqual(result["auction_status"], "sold_third_party")

    def test_convert_missing_address_returns_none(self):
        converter = ProspectConverter(self.job)
        record = {
            "auction_id": "123",
            "address": "",
            "case_number": "C-001",
            "auction_date": "03/01/2026",
            "status": "Sold",
        }
        result = converter.convert_auction_to_prospect(record)
        self.assertIsNone(result)

    def test_normalize_status_mapping(self):
        converter = ProspectConverter(self.job)
        self.assertEqual(converter._normalize_status("Sold"), "sold_third_party")
        self.assertEqual(converter._normalize_status("Canceled"), "cancelled")
        self.assertEqual(converter._normalize_status("Postponed"), "postponed")
        self.assertEqual(converter._normalize_status("Scheduled"), "scheduled")
        self.assertEqual(converter._normalize_status("Unknown"), "scheduled")

    def test_parse_currency(self):
        converter = ProspectConverter(self.job)
        self.assertEqual(converter._parse_currency("$1,234.56"), 1234.56)
        self.assertEqual(converter._parse_currency("$50000"), 50000.0)
        self.assertIsNone(converter._parse_currency(""))
        self.assertIsNone(converter._parse_currency(None))

    def test_parse_date(self):
        converter = ProspectConverter(self.job)
        result = converter._parse_date("03/15/2026")
        self.assertEqual(result, date(2026, 3, 15))
        self.assertIsNone(converter._parse_date("bad-date"))


# ============================================================================
# JOB EXECUTE API ENDPOINT TESTS
# ============================================================================

class JobExecuteAPIViewTest(TestCase):
    """Test POST /api/v2/jobs/<pk>/execute/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.client = Client()
        self.client.login(username="admin", password="pass")
        self.job = ScrapingJob.objects.create(
            name="API Exec",
            state="FL",
            county="Miami-Dade",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
        )

    @patch("apps.scraper.views.execute_job_async", return_value=True)
    def test_execute_returns_success(self, mock_exec):
        url = reverse("scraper:job_execute_api", kwargs={"pk": self.job.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("status_url", data)

    @patch("apps.scraper.views.execute_job_async", return_value=False)
    def test_execute_already_running_returns_400(self, mock_exec):
        url = reverse("scraper:job_execute_api", kwargs={"pk": self.job.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])

    def test_execute_nonexistent_job_returns_404(self):
        url = reverse("scraper:job_execute_api", kwargs={"pk": uuid.uuid4()})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_non_admin_cannot_execute(self):
        user = User.objects.create_user(username="regular", password="pass")
        c = Client()
        c.login(username="regular", password="pass")
        url = reverse("scraper:job_execute_api", kwargs={"pk": self.job.pk})
        resp = c.post(url)
        self.assertIn(resp.status_code, [302, 403])


# ============================================================================
# JOB RETRY API ENDPOINT TESTS
# ============================================================================

class JobRetryAPIViewTest(TestCase):
    """Test POST /api/v2/jobs/<pk>/retry/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.client = Client()
        self.client.login(username="admin", password="pass")
        self.job = ScrapingJob.objects.create(
            name="Retry Test",
            state="FL",
            county="Miami-Dade",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
            status="failed",
        )

    @patch("apps.scraper.views.retry_failed_job", return_value=True)
    def test_retry_failed_job_success(self, mock_retry):
        url = reverse("scraper:job_retry_api", kwargs={"pk": self.job.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

    def test_retry_non_failed_job_returns_400(self):
        self.job.status = "pending"
        self.job.save()
        url = reverse("scraper:job_retry_api", kwargs={"pk": self.job.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])

    @patch("apps.scraper.views.retry_failed_job", return_value=False)
    def test_retry_max_retries_reached_returns_400(self, mock_retry):
        url = reverse("scraper:job_retry_api", kwargs={"pk": self.job.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)

    def test_retry_nonexistent_job_returns_404(self):
        url = reverse("scraper:job_retry_api", kwargs={"pk": uuid.uuid4()})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)


# ============================================================================
# JOB EXECUTOR (THREADPOOL) TESTS
# ============================================================================

class JobExecutorTest(TestCase):
    """Test the JobExecutor singleton and thread management."""

    def setUp(self):
        self.job = ScrapingJob.objects.create(
            name="Executor Test",
            state="FL",
            county="Test",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
        )

    def test_singleton_pattern(self):
        # Reset singleton for clean test
        JobExecutor._instance = None
        JobExecutor._instance_initialized = False if hasattr(JobExecutor, '_instance_initialized') else None

        exec1 = JobExecutor(max_workers=2)
        exec2 = JobExecutor(max_workers=2)
        self.assertIs(exec1, exec2)

        # Cleanup
        exec1.shutdown(wait=False)
        JobExecutor._instance = None

    def test_submit_nonexistent_job_returns_false(self):
        JobExecutor._instance = None
        executor = JobExecutor(max_workers=1)
        result = executor.submit_job(str(uuid.uuid4()))
        self.assertFalse(result)
        executor.shutdown(wait=False)
        JobExecutor._instance = None

    def test_get_job_status_nonexistent_returns_error(self):
        JobExecutor._instance = None
        executor = JobExecutor(max_workers=1)
        status = executor.get_job_status(str(uuid.uuid4()))
        self.assertIn("error", status)
        executor.shutdown(wait=False)
        JobExecutor._instance = None

    def test_get_active_jobs_initially_empty(self):
        JobExecutor._instance = None
        executor = JobExecutor(max_workers=1)
        self.assertEqual(executor.get_active_jobs(), [])
        executor.shutdown(wait=False)
        JobExecutor._instance = None


# ============================================================================
# JOB BATCH PROCESSOR TESTS
# ============================================================================

class JobBatchProcessorTest(TestCase):
    """Test JobBatchProcessor for processing pending jobs."""

    def setUp(self):
        JobExecutor._instance = None

    def tearDown(self):
        try:
            executor = JobExecutor(max_workers=1)
            executor.shutdown(wait=False)
        except Exception:
            pass
        JobExecutor._instance = None

    @patch.object(JobExecutor, "submit_job", return_value=True)
    def test_process_pending_jobs(self, mock_submit):
        for i in range(3):
            ScrapingJob.objects.create(
                name=f"Pending {i}",
                state="FL",
                county="Test",
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 7),
                status="pending",
            )
        processor = JobBatchProcessor(batch_size=10)
        result = processor.process_pending_jobs()
        self.assertEqual(result["submitted"], 3)

    @patch.object(JobExecutor, "submit_job", return_value=True)
    def test_process_pending_jobs_with_limit(self, mock_submit):
        for i in range(5):
            ScrapingJob.objects.create(
                name=f"Pending {i}",
                state="FL",
                county="Test",
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 7),
                status="pending",
            )
        processor = JobBatchProcessor(batch_size=10)
        result = processor.process_pending_jobs(limit=2)
        self.assertEqual(result["submitted"], 2)

    def test_process_skips_non_pending_jobs(self):
        ScrapingJob.objects.create(
            name="Running",
            state="FL",
            county="Test",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
            status="running",
        )
        ScrapingJob.objects.create(
            name="Completed",
            state="FL",
            county="Test",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
            status="completed",
        )
        processor = JobBatchProcessor(batch_size=10)
        result = processor.process_pending_jobs()
        self.assertEqual(result["submitted"], 0)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class HelperFunctionTest(TestCase):
    """Test module-level helper functions."""

    def setUp(self):
        JobExecutor._instance = None

    def tearDown(self):
        try:
            executor = JobExecutor(max_workers=1)
            executor.shutdown(wait=False)
        except Exception:
            pass
        JobExecutor._instance = None

    @patch.object(JobExecutor, "submit_job", return_value=True)
    def test_execute_job_async_delegates_to_executor(self, mock_submit):
        result = execute_job_async(str(uuid.uuid4()))
        self.assertTrue(result)
        mock_submit.assert_called_once()

    @patch.object(JobExecutor, "get_job_status", return_value={"status": "pending"})
    def test_get_job_status_polling_delegates(self, mock_status):
        result = get_job_status_polling(str(uuid.uuid4()))
        self.assertEqual(result["status"], "pending")
