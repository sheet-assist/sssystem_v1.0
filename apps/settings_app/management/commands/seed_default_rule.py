from django.core.management.base import BaseCommand
from apps.settings_app.models import FilterCriteria
from apps.locations.models import State
import datetime


class Command(BaseCommand):
    help = 'Seed default filter rule: FL TD min_surplus > 10000, date >= 2024-01-01'

    def handle(self, *args, **options):
        fl_state, _ = State.objects.get_or_create(name='Florida', defaults={'abbreviation': 'FL'})
        rule, created = FilterCriteria.objects.get_or_create(
            name='Florida TD Default',
            state=fl_state,
            defaults={
                'prospect_types': ['TD'],
                'surplus_amount_min': 10000.00,
                'min_date': datetime.date(2024, 1, 1),
                'status_types': ['Live', 'Upcoming'],
                'is_active': True,
            }
        )
        if not created:
            rule.prospect_types = ['TD']
            rule.surplus_amount_min = 10000.00
            rule.min_date = datetime.date(2024, 1, 1)
            rule.status_types = ['Live', 'Upcoming']
            rule.is_active = True
            rule.save()

        self.stdout.write(self.style.SUCCESS(f'Rule seeded: {rule.name}'))
