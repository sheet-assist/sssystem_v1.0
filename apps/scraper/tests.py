from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import datetime, date
from decimal import Decimal

from apps.locations.models import State, County
from apps.scraper.models import ScrapeJob, ScrapeLog
from apps.scraper.parsers import (
    parse_currency, parse_calendar_page, normalize_prospect_data, calculate_surplus
)
from apps.prospects.models import Prospect

User = get_user_model()


class ParserTests(TestCase):
    def test_parse_currency_valid(self):
        """Parse valid currency strings."""
        self.assertEqual(parse_currency('$1,234.56'), Decimal('1234.56'))
        self.assertEqual(parse_currency('$10000'), Decimal('10000'))
        self.assertEqual(parse_currency('1000.00'), Decimal('1000.00'))

    def test_parse_currency_invalid(self):
        """Parse invalid currency returns None."""
        self.assertIsNone(parse_currency(''))
        self.assertIsNone(parse_currency('abc'))

    def test_parse_calendar_page(self):
        """Parse mock calendar HTML and extract auctions."""
        html = '''
        <div class="AUCTION_ITEM" aid="12345">
            <div class="ASTAT_MSGB">Sale Time: 11:00 AM</div>
            <div class="AUCTION_DETAILS">
                <table class="ad_tab">
                    <tr><td>Case #</td><td>2024-001234</td></tr>
                    <tr><td>Parcel ID</td><td>0001-0001-001</td></tr>
                    <tr><td>Final Judgment</td><td>$50,000.00</td></tr>
                    <tr><td>Property Address</td><td>123 Main St</td></tr>
                    <tr><td></td><td>Miami, FL 33101</td></tr>
                </table>
            </div>
        </div>
        '''
        auctions = parse_calendar_page(html, 'miamidade')
        self.assertEqual(len(auctions), 1)
        self.assertEqual(auctions[0]['auction_id'], '12345')
        self.assertEqual(auctions[0]['case_number'], '2024-001234')
        self.assertEqual(auctions[0]['parcel_id'], '0001-0001-001')
        self.assertEqual(auctions[0]['final_judgment_amount'], Decimal('50000.00'))

    def test_normalize_prospect_data(self):
        """Normalize raw auction data to prospect fields."""
        raw = {
            'auction_id': '123',
            'case_number': '2024-456',
            'county_code': 'miamidade',
            'property_address': '123 Main St',
            'city_state_zip': 'Miami, FL 33101',
            'parcel_id': '001-001-001',
            'final_judgment_amount': Decimal('50000'),
            'plaintiff_max_bid': Decimal('60000'),
            'assessed_value': Decimal('100000'),
            'auction_status': 'scheduled',
        }
        
        prospect = normalize_prospect_data(raw, date(2026, 3, 15), 'TD')
        self.assertEqual(prospect['prospect_type'], 'TD')
        self.assertEqual(prospect['case_number'], '2024-456')
        self.assertEqual(prospect['property_address'], '123 Main St')
        self.assertEqual(prospect['auction_date'], date(2026, 3, 15))

    def test_calculate_surplus(self):
        """Calculate estimated surplus."""
        data = {
            'assessed_value': Decimal('100000'),
            'opening_bid': Decimal('70000'),
        }
        surplus = calculate_surplus(data)
        self.assertEqual(surplus, Decimal('30000'))

    def test_calculate_surplus_missing_fields(self):
        """Calculate surplus with missing fields returns None."""
        data = {'assessed_value': Decimal('100000')}
        self.assertIsNone(calculate_surplus(data))


class ScrapeJobModelTests(TestCase):
    def setUp(self):
        self.state = State.objects.create(name='Florida', abbreviation='FL', is_active=True)
        self.county = County.objects.create(
            state=self.state, name='Miami-Dade', slug='miamidade', is_active=True
        )

    def test_scrape_job_creation(self):
        """Create a scrape job."""
        job = ScrapeJob.objects.create(
            county=self.county,
            job_type='TD',
            target_date=date(2026, 3, 15),
            status='pending'
        )
        self.assertEqual(job.status, 'pending')
        self.assertEqual(job.prospects_created, 0)

    def test_scrape_job_str(self):
        """String representation of scrape job."""
        job = ScrapeJob.objects.create(
            county=self.county,
            job_type='TD',
            target_date=date(2026, 3, 15),
        )
        self.assertIn('Miami-Dade', str(job))
        self.assertIn('TD', str(job))

    def test_scrape_log_creation(self):
        """Create scrape logs."""
        job = ScrapeJob.objects.create(
            county=self.county,
            job_type='TD',
            target_date=date(2026, 3, 15),
        )
        log = ScrapeLog.objects.create(
            job=job,
            level='info',
            message='Test log message'
        )
        self.assertEqual(log.level, 'info')
        self.assertEqual(log.job, job)
        self.assertEqual(ScrapeLog.objects.filter(job=job).count(), 1)


class ScrapeJobExecutionTests(TestCase):
    def setUp(self):
        self.state = State.objects.create(name='Florida', abbreviation='FL', is_active=True)
        self.county = County.objects.create(
            state=self.state, name='Miami-Dade', slug='miamidade', is_active=True,
            taxdeed_url='https://miamidade.realtaxdeed.com'
        )
        self.user = User.objects.create_user(username='scraper', password='pass123')

    def test_scrape_job_status_transitions(self):
        """Test scrape job status transitions."""
        job = ScrapeJob.objects.create(
            county=self.county,
            job_type='TD',
            target_date=date(2026, 3, 15),
            triggered_by=self.user,
        )
        self.assertEqual(job.status, 'pending')
        
        job.status = 'running'
        job.save()
        self.assertEqual(job.status, 'running')
        
        job.status = 'completed'
        job.save()
        self.assertEqual(job.status, 'completed')

    def test_scrape_job_record_counts(self):
        """Update record counts on job."""
        job = ScrapeJob.objects.create(
            county=self.county,
            job_type='TD',
            target_date=date(2026, 3, 15),
        )
        job.prospects_created = 5
        job.prospects_qualified = 3
        job.prospects_disqualified = 2
        job.save()
        
        job.refresh_from_db()
        self.assertEqual(job.prospects_created, 5)
        self.assertEqual(job.prospects_qualified, 3)
        self.assertEqual(job.prospects_disqualified, 2)

