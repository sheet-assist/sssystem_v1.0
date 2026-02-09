from django.core.management.base import BaseCommand
from apps.locations.models import State, County
from django.utils.text import slugify

# Minimal list of FL counties and their assumed subdomain slugs for realforeclose/realtaxdeed
FL_COUNTIES = [
    'Alachua', 'Baker', 'Bay', 'Bradford', 'Brevard', 'Broward', 'Calhoun', 'Charlotte', 'Citrus', 'Clay',
    'Collier', 'Columbia', 'DeSoto', 'Dixie', 'Duval', 'Escambia', 'Flagler', 'Franklin', 'Gadsden', 'Gilchrist',
    'Glades', 'Gulf', 'Hamilton', 'Hardee', 'Hendry', 'Hernando', 'Highlands', 'Hillsborough', 'Holmes', 'Indian River',
    'Jackson', 'Jefferson', 'Lafayette', 'Lake', 'Lee', 'Leon', 'Levy', 'Liberty', 'Madison', 'Manatee',
    'Marion', 'Martin', 'Miami-Dade', 'Monroe', 'Nassau', 'Okaloosa', 'Okeechobee', 'Orange', 'Osceola', 'Palm Beach',
    'Pasco', 'Pinellas', 'Polk', 'Putnam', 'St. Johns', 'St. Lucie', 'Santa Rosa', 'Sarasota', 'Seminole', 'Sumter',
    'Suwannee', 'Taylor', 'Union', 'Volusia', 'Wakulla', 'Walton', 'Washington'
]


class Command(BaseCommand):
    help = 'Load 67 Florida counties with default URLs for realforeclose/realtaxdeed (idempotent).'

    def handle(self, *args, **options):
        state, _ = State.objects.get_or_create(name='Florida', defaults={'abbreviation': 'FL'})
        created = 0
        for name in FL_COUNTIES:
            slug = slugify(name)
            foreclosure_url = f'https://{slug}.realforeclose.com/'
            taxdeed_url = f'https://{slug}.realtaxdeed.com/'
            defaults = {
                'fips_code': '',
                'is_active': True,
                'available_prospect_types': ['TD'],
                'uses_realtdm': False,
                'uses_auction_calendar': False,
                'auction_calendar_url': '',
                'realtdm_url': '',
                'foreclosure_url': foreclosure_url,
                'taxdeed_url': taxdeed_url,
                'platform': 'realforeclose',
            }
            obj, was_created = County.objects.get_or_create(state=state, slug=slug, defaults={**defaults, 'name': name})
            if not was_created:
                # update URLs if missing
                changed = False
                for k, v in defaults.items():
                    if getattr(obj, k) in (None, '', []) and v:
                        setattr(obj, k, v)
                        changed = True
                if changed:
                    obj.save()
            else:
                created += 1

        self.stdout.write(self.style.SUCCESS(f'Loaded FL counties. Created: {created}'))
