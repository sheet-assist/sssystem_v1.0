from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.locations.models import County, State
from apps.prospects.models import Prospect

from .engine import build_auction_url, get_base_url
from .models import ScrapeJob, ScrapeLog
from .parsers import (
    normalize_prospect_data,
    parse_calendar_page,
    parse_city_state_zip,
    parse_currency,
)

User = get_user_model()


# --- Sample HTML mimicking realforeclose.com ---
SAMPLE_HTML = """
<div class="AUCTION_ITEM" aid="12345">
    <div class="ASTAT_MSGB">Sale Time: 11:00 AM</div>
    <div class="AUCTION_DETAILS">
        <table class="ad_tab">
            <tr><td>Auction Type</td><td>FORECLOSURE</td></tr>
            <tr><td>Case #</td><td>2024-001234</td></tr>
            <tr><td>Final Judgment Amount</td><td>$50,000.00</td></tr>
            <tr><td>Parcel ID</td><td>0001-0001-001</td></tr>
            <tr><td>Property Address</td><td>123 Main St</td></tr>
            <tr><td></td><td>Miami, FL 33101</td></tr>
            <tr><td>Assessed Value</td><td>$120,000.00</td></tr>
            <tr><td>Plaintiff Max Bid</td><td>$60,000.00</td></tr>
        </table>
    </div>
    <div class="AUCTION_STATS">
        <div class="ASTAT_MSGD">$75,000.00</div>
        <div class="ASTAT_MSG_SOLDTO_MSG">Third Party</div>
    </div>
</div>
<div class="AUCTION_ITEM" aid="99999">
    <div class="ASTAT_MSGB">Canceled</div>
    <div class="AUCTION_DETAILS">
        <table class="ad_tab">
            <tr><td>Case #</td><td>2024-005678</td></tr>
            <tr><td>Property Address</td><td>456 Oak Ave</td></tr>
        </table>
    </div>
</div>
"""


class ParseCurrencyTest(TestCase):
    def test_valid_amounts(self):
        self.assertEqual(parse_currency("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_currency("$10000"), Decimal("10000"))
        self.assertEqual(parse_currency("1000.00"), Decimal("1000.00"))

    def test_returns_none_for_empty(self):
        self.assertIsNone(parse_currency(""))
        self.assertIsNone(parse_currency(None))

    def test_returns_none_for_garbage(self):
        self.assertIsNone(parse_currency("abc"))


class ParseCityStateZipTest(TestCase):
    def test_full_address(self):
        city, state, zip_code = parse_city_state_zip("Miami, FL 33101")
        self.assertEqual(city, "Miami")
        self.assertEqual(state, "FL")
        self.assertEqual(zip_code, "33101")

    def test_city_only(self):
        city, state, zip_code = parse_city_state_zip("Orlando")
        self.assertEqual(city, "Orlando")
        self.assertEqual(state, "")
        self.assertEqual(zip_code, "")

    def test_empty(self):
        city, state, zip_code = parse_city_state_zip("")
        self.assertEqual(city, "")


class ParseCalendarPageTest(TestCase):
    def test_parses_two_auctions(self):
        auctions = parse_calendar_page(SAMPLE_HTML)
        self.assertEqual(len(auctions), 2)

    def test_first_auction_fields(self):
        auctions = parse_calendar_page(SAMPLE_HTML)
        a = auctions[0]
        self.assertEqual(a["auction_id"], "12345")
        self.assertEqual(a["case_number"], "2024-001234")
        self.assertEqual(a["parcel_id"], "0001-0001-001")
        self.assertEqual(a["property_address"], "123 Main St")
        self.assertEqual(a["auction_type"], "FORECLOSURE")
        self.assertEqual(a["final_judgment_amount"], Decimal("50000.00"))
        self.assertEqual(a["assessed_value"], Decimal("120000.00"))
        self.assertEqual(a["plaintiff_max_bid"], Decimal("60000.00"))
        self.assertEqual(a["city_state_zip"], "Miami, FL 33101")

    def test_sold_details(self):
        auctions = parse_calendar_page(SAMPLE_HTML)
        a = auctions[0]
        self.assertEqual(a["auction_status"], "sold")
        self.assertEqual(a["sold_amount"], Decimal("75000.00"))
        self.assertEqual(a["sold_to"], "Third Party")

    def test_cancelled_status(self):
        auctions = parse_calendar_page(SAMPLE_HTML)
        a = auctions[1]
        self.assertEqual(a["auction_status"], "cancelled")
        self.assertEqual(a["case_number"], "2024-005678")

    def test_empty_html(self):
        auctions = parse_calendar_page("<html></html>")
        self.assertEqual(len(auctions), 0)


class NormalizeProspectDataTest(TestCase):
    def test_normalizes_all_fields(self):
        raw = {
            "auction_id": "123",
            "case_number": "2024-456",
            "auction_type": "FORECLOSURE",
            "property_address": "123 Main St",
            "city_state_zip": "Miami, FL 33101",
            "parcel_id": "001-001-001",
            "final_judgment_amount": Decimal("50000"),
            "plaintiff_max_bid": Decimal("60000"),
            "assessed_value": Decimal("100000"),
            "auction_status": "scheduled",
            "sold_amount": None,
            "sold_to": "",
            "start_time": "11:00 AM",
        }
        result = normalize_prospect_data(raw, date(2026, 3, 15), "TD", "https://example.com")
        self.assertEqual(result["prospect_type"], "TD")
        self.assertEqual(result["case_number"], "2024-456")
        self.assertEqual(result["auction_type"], "FORECLOSURE")
        self.assertEqual(result["city"], "Miami")
        self.assertEqual(result["state"], "FL")
        self.assertEqual(result["zip_code"], "33101")
        self.assertEqual(result["auction_date"], date(2026, 3, 15))
        self.assertEqual(result["source_url"], "https://example.com")
        self.assertEqual(result["sold_to"], "")
        self.assertIsInstance(result["raw_data"], dict)


class EngineUrlTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            taxdeed_url="https://miami-dade.realtaxdeed.com",
            foreclosure_url="https://miami-dade.realforeclose.com",
        )

    def test_get_base_url_td(self):
        url = get_base_url(self.county, "TD")
        self.assertEqual(url, "https://miami-dade.realtaxdeed.com")

    def test_get_base_url_foreclosure(self):
        url = get_base_url(self.county, "MF")
        self.assertEqual(url, "https://miami-dade.realforeclose.com")

    def test_get_base_url_missing_raises(self):
        empty_county = County.objects.create(
            state=self.state, name="Empty", slug="empty",
        )
        with self.assertRaises(ValueError):
            get_base_url(empty_county, "TD")

    def test_build_auction_url(self):
        url = build_auction_url("https://miami-dade.realtaxdeed.com", date(2026, 3, 15))
        self.assertEqual(
            url,
            "https://miami-dade.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=03/15/2026",
        )


class ScrapeJobModelTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            taxdeed_url="https://miami-dade.realtaxdeed.com",
        )

    def test_create_job(self):
        job = ScrapeJob.objects.create(
            county=self.county, job_type="TD", target_date=date(2026, 3, 15),
        )
        self.assertEqual(job.status, "pending")
        self.assertIn("Miami-Dade", str(job))

    def test_create_job_with_date_range(self):
        job = ScrapeJob.objects.create(
            county=self.county, job_type="TD",
            target_date=date(2026, 3, 15), end_date=date(2026, 3, 20),
        )
        self.assertEqual(job.end_date, date(2026, 3, 20))

    def test_scrape_log(self):
        job = ScrapeJob.objects.create(
            county=self.county, job_type="TD", target_date=date(2026, 3, 15),
        )
        log = ScrapeLog.objects.create(job=job, level="info", message="Test")
        self.assertEqual(job.logs.count(), 1)
        self.assertIn("INFO", str(log))


class ScraperViewsTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            taxdeed_url="https://miami-dade.realtaxdeed.com",
        )
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.client = Client()
        self.client.login(username="admin", password="pass")

    def test_dashboard(self):
        resp = self.client.get("/scraper/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Scraper Dashboard")

    def test_job_list(self):
        ScrapeJob.objects.create(
            county=self.county, job_type="TD", target_date=date(2026, 3, 15),
        )
        resp = self.client.get("/scraper/jobs/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Miami-Dade")

    def test_job_create(self):
        resp = self.client.post("/scraper/jobs/create/", {
            "county": self.county.pk,
            "job_type": "TD",
            "target_date": "2026-03-15",
        })
        self.assertEqual(resp.status_code, 302)
        job = ScrapeJob.objects.first()
        self.assertEqual(job.county, self.county)
        self.assertEqual(job.triggered_by, self.admin)

    def test_job_create_with_date_range(self):
        resp = self.client.post("/scraper/jobs/create/", {
            "county": self.county.pk,
            "job_type": "TD",
            "target_date": "2026-03-15",
            "end_date": "2026-03-20",
        })
        self.assertEqual(resp.status_code, 302)
        job = ScrapeJob.objects.first()
        self.assertEqual(job.end_date, date(2026, 3, 20))

    def test_job_create_invalid_date_range(self):
        resp = self.client.post("/scraper/jobs/create/", {
            "county": self.county.pk,
            "job_type": "TD",
            "target_date": "2026-03-20",
            "end_date": "2026-03-15",
        })
        self.assertEqual(resp.status_code, 200)  # stays on form
        self.assertEqual(ScrapeJob.objects.count(), 0)

    def test_job_detail(self):
        job = ScrapeJob.objects.create(
            county=self.county, job_type="TD", target_date=date(2026, 3, 15),
        )
        resp = self.client.get(f"/scraper/jobs/{job.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Miami-Dade")

    def test_non_admin_cannot_access(self):
        user = User.objects.create_user(username="worker", password="pass")
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.get("/scraper/dashboard/")
        self.assertEqual(resp.status_code, 403)
