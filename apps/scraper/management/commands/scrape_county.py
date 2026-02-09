from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from apps.scraper.models import ScrapeJob
from apps.scraper.engine import run_scrape_job
from apps.locations.models import County


class Command(BaseCommand):
    help = 'Scrape auctions from realforeclose.com or realtaxdeed.com'

    def add_arguments(self, parser):
        parser.add_argument('--county', type=str, required=True, help='County slug (e.g., miamidade)')
        parser.add_argument('--date', type=str, required=True, help='Auction date (YYYY-MM-DD)')
        parser.add_argument('--type', type=str, default='TD', choices=['TD', 'TL', 'SS', 'MF'],
                          help='Prospect type')

    def handle(self, *args, **options):
        county_slug = options['county']
        auction_date_str = options['date']
        job_type = options['type']
        
        try:
            county = County.objects.get(slug=county_slug)
        except County.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'County {county_slug} not found'))
            return
        
        try:
            auction_date = datetime.strptime(auction_date_str, '%Y-%m-%d').date()
        except ValueError:
            self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
            return
        
        # Create or get existing job
        job, created = ScrapeJob.objects.get_or_create(
            county=county,
            job_type=job_type,
            target_date=auction_date,
            defaults={'status': 'pending'}
        )
        
        if not created and job.status in ['running', 'completed']:
            self.stdout.write(self.style.WARNING(f'Job already exists with status {job.status}'))
            return
        
        self.stdout.write(f'Running scrape job {job.pk} for {county.name} on {auction_date}')
        
        try:
            run_scrape_job(job)
            self.stdout.write(self.style.SUCCESS(
                f'Scrape completed: {job.prospects_created} created, '
                f'{job.prospects_updated} updated, {job.prospects_qualified} qualified'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Scrape failed: {str(e)}'))
