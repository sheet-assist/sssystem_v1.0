from django.core.management.base import BaseCommand

from apps.locations.models import State
from apps.scraper.models import CountyScrapeURL


class Command(BaseCommand):
    help = "Copy Mortgage Foreclosure base URLs to Tax Deed entries for a given state (default FL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--state",
            default="FL",
            help="State abbreviation to process (default: FL).",
        )
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Create TD records when missing instead of skipping them.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the planned changes without saving them.",
        )

    def handle(self, *args, **options):
        state_code = options["state"].upper()
        create_missing = options["create_missing"]
        dry_run = options["dry_run"]

        try:
            state = State.objects.get(abbreviation=state_code)
        except State.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"State '{state_code}' not found."))
            return

        mf_urls = (
            CountyScrapeURL.objects.filter(state=state, url_type="MF")
            .select_related("county")
            .order_by("county__name")
        )

        if not mf_urls:
            self.stdout.write(self.style.WARNING("No MF URLs found; nothing to sync."))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Syncing TD base URLs for {state_code} (dry_run={dry_run}, create_missing={create_missing})"
            )
        )

        updated = 0
        created = 0
        skipped = 0

        for mf_entry in mf_urls:
            td_entry = (
                CountyScrapeURL.objects.filter(county=mf_entry.county, url_type="TD")
                .select_related("county")
                .first()
            )

            if td_entry:
                if td_entry.base_url == mf_entry.base_url:
                    skipped += 1
                    continue

                self.stdout.write(
                    f"Updating TD URL for {mf_entry.county.name}: {td_entry.base_url} -> {mf_entry.base_url}"
                )
                updated += 1
                if not dry_run:
                    td_entry.base_url = mf_entry.base_url
                    td_entry.state = state
                    td_entry.save(update_fields=["base_url", "state", "updated_at"])
            else:
                if not create_missing:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"No TD entry for {mf_entry.county.name}; use --create-missing to add it."
                        )
                    )
                    continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Creating TD URL for {mf_entry.county.name}: {mf_entry.base_url}"
                    )
                )
                created += 1
                if not dry_run:
                    CountyScrapeURL.objects.create(
                        county=mf_entry.county,
                        state=state,
                        url_type="TD",
                        base_url=mf_entry.base_url,
                        is_active=mf_entry.is_active,
                        notes="Auto-synced from MF via sync_td_urls",
                    )

        summary = f"Done. {updated} updated, {created} created, {skipped} unchanged."
        if dry_run:
            summary += " (dry run)"
        self.stdout.write(self.style.SUCCESS(summary))
