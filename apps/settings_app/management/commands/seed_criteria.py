from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.locations.models import State
from apps.settings_app.models import FilterCriteria


class Command(BaseCommand):
    help = "Seed default filter criteria for FL Tax Deeds (idempotent)."

    def handle(self, *args, **options):
        fl = State.objects.filter(abbreviation="FL").first()
        if not fl:
            self.stdout.write(self.style.WARNING("Florida not found. Run load_states first."))
            return

        _, created = FilterCriteria.objects.get_or_create(
            name="Florida TD Default",
            state=fl,
            defaults={
                "prospect_types": ["TD"],
                "surplus_amount_min": Decimal("10000"),
                "min_date": date(2024, 1, 1),
                "status_types": ["Live", "Upcoming"],
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Default FL TD rule created."))
        else:
            self.stdout.write(self.style.WARNING("Default FL TD rule already exists."))
