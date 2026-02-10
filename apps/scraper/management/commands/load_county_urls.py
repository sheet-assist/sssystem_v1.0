from django.core.management.base import BaseCommand
from apps.locations.models import County, State
from apps.scraper.models import CountyScrapeURL


class Command(BaseCommand):
    """
    Management command to load county scrape URLs
    
    Usage: python manage.py load_county_urls
    """
    
    help = 'Load Florida county URLs for scraping from RealForeclose'
    
    # Florida county URL mapping
    FLORIDA_COUNTY_URLS = {
        'Miami-Dade': 'https://www.miamidade.realforeclose.com/',
        'Broward': 'https://www.broward.realforeclose.com/',
        'Palm Beach': 'https://www.palmbeach.realforeclose.com/',
        'Hillsborough': 'https://www.hillsborough.realforeclose.com/',
        'Orange': 'https://www.orange.realforeclose.com/',
        'Duval': 'https://www.duval.realforeclose.com/',
        'Pinellas': 'https://www.pinellas.realforeclose.com/',
        'Lee': 'https://www.lee.realforeclose.com/',
        'Polk': 'https://www.polk.realforeclose.com/',
        'Volusia': 'https://www.volusia.realforeclose.com/',
        'Marion': 'https://www.marion.realforeclose.com/',
        'Brevard': 'https://www.brevard.realforeclose.com/',
        'Alachua': 'https://www.alachua.realforeclose.com/',
        'Clay': 'https://www.clay.realforeclose.com/',
        'Escambia': 'https://www.escambia.realforeclose.com/',
        'Santa Rosa': 'https://www.santarosa.realforeclose.com/',
        'Okaloosa': 'https://www.okaloosa.realforeclose.com/',
        'Leon': 'https://www.leon.realforeclose.com/',
        'Gadsden': 'https://www.gadsden.realforeclose.com/',
        'Bay': 'https://www.bay.realforeclose.com/',
        'Pasco': 'https://www.pasco.realforeclose.com/',
        'Hernando': 'https://www.hernando.realforeclose.com/',
        'Citrus': 'https://www.citrus.realforeclose.com/',
        'Sumter': 'https://www.sumter.realforeclose.com/',
        'Lake': 'https://www.lake.realforeclose.com/',
        'Osceola': 'https://www.osceola.realforeclose.com/',
        'Seminole': 'https://www.seminole.realforeclose.com/',
        'Sarasota': 'https://www.sarasota.realforeclose.com/',
        'Charlotte': 'https://www.charlotte.realforeclose.com/',
        'Collier': 'https://www.collier.realforeclose.com/',
        'Glades': 'https://www.glades.realforeclose.com/',
        'Hendry': 'https://www.hendry.realforeclose.com/',
        'Highlands': 'https://www.highlands.realforeclose.com/',
        'Indian River': 'https://www.indianriver.realforeclose.com/',
        'Martin': 'https://www.martin.realforeclose.com/',
        'Okeechobee': 'https://www.okeechobee.realforeclose.com/',
        'St. Lucie': 'https://www.stlucie.realforeclose.com/',
        'Union': 'https://www.union.realforeclose.com/',
        'Bradford': 'https://www.bradford.realforeclose.com/',
        'Gilchrist': 'https://www.gilchrist.realforeclose.com/',
        'Levy': 'https://www.levy.realforeclose.com/',
        'Nassau': 'https://www.nassau.realforeclose.com/',
        'Baker': 'https://www.baker.realforeclose.com/',
        'Columbia': 'https://www.columbia.realforeclose.com/',
        'Dixie': 'https://www.dixie.realforeclose.com/',
        'Flagler': 'https://www.flagler.realforeclose.com/',
        'Putnam': 'https://www.putnam.realforeclose.com/',
        'St. Johns': 'https://www.stjohns.realforeclose.com/',
        'Suwannee': 'https://www.suwannee.realforeclose.com/',
        'Taylor': 'https://www.taylor.realforeclose.com/',
        'Jefferson': 'https://www.jefferson.realforeclose.com/',
        'Madison': 'https://www.madison.realforeclose.com/',
        'Hamilton': 'https://www.hamilton.realforeclose.com/',
        'Lafayette': 'https://www.lafayette.realforeclose.com/',
        'Gilchrist': 'https://www.gilchrist.realforeclose.com/',
        'Calhoun': 'https://www.calhoun.realforeclose.com/',
        'Holmes': 'https://www.holmes.realforeclose.com/',
        'Jackson': 'https://www.jackson.realforeclose.com/',
        'Liberty': 'https://www.liberty.realforeclose.com/',
        'Wakulla': 'https://www.wakulla.realforeclose.com/',
        'Talbot': 'https://www.talbot.realforeclose.com/',
        'Franklin': 'https://www.franklin.realforeclose.com/',
        'Gulf': 'https://www.gulf.realforeclose.com/',
        'Washington': 'https://www.washington.realforeclose.com/',
        'De Soto': 'https://www.desoto.realforeclose.com/',
    }
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--state',
            type=str,
            default='FL',
            help='State abbreviation (default: FL)'
        )
        parser.add_argument(
            '--type',
            type=str,
            default='MF',
            choices=['TD', 'TL', 'SS', 'MF'],
            help='Job/URL type (default: MF). TD=Tax Deed, TL=Tax Lien, SS=Sheriff Sale, MF=Mortgage Foreclosure'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload existing URLs'
        )

    def handle(self, *args, **options):
        state_code = options['state']
        url_type = options['type']
        force = options['force']

        try:
            state = State.objects.get(abbreviation=state_code)
        except State.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'State with code {state_code} not found')
            )
            return

        self.stdout.write(f'Loading {url_type} URLs for {state_code}...\n')

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for county_name, base_url in self.FLORIDA_COUNTY_URLS.items():
            try:
                county = County.objects.get(name=county_name, state=state)
            except County.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f'County {county_name} not found in {state_code}. Skipping.'
                    )
                )
                skipped_count += 1
                continue

            # Check if URL already exists for this county + type
            url_obj, created = CountyScrapeURL.objects.get_or_create(
                county=county,
                url_type=url_type,
                defaults={
                    'state': state,
                    'base_url': base_url,
                    'is_active': True,
                }
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'[OK] Created: {county_name} ({url_type}) -> {base_url}'
                    )
                )
                created_count += 1
            elif force:
                url_obj.base_url = base_url
                url_obj.is_active = True
                url_obj.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'[OK] Updated: {county_name} ({url_type}) -> {base_url}'
                    )
                )
                updated_count += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'[SKIP] Skipped: {county_name} ({url_type}) (already exists)'
                    )
                )
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n[DONE] Summary for {url_type}:\n'
                f'  Created: {created_count}\n'
                f'  Updated: {updated_count}\n'
                f'  Skipped: {skipped_count}\n'
                f'  Total: {created_count + updated_count + skipped_count}'
            )
        )
