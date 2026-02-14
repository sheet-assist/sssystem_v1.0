from django.contrib import admin

from .models import County, State


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "is_active")
    search_fields = ("name", "abbreviation")


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "slug", "is_active", "platform", "last_scraped")
    list_filter = ("state", "is_active", "platform")
    search_fields = ("name", "slug", "fips_code")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (None, {"fields": ("state", "name", "slug", "fips_code", "is_active")}),
        ("Configuration", {
            "fields": (
                "available_prospect_types", "platform",
                "uses_realtdm", "uses_auction_calendar",
                "auction_calendar_url", "realtdm_url",
                "foreclosure_url", "taxdeed_url",
            )
        }),
        ("Scraping", {"fields": ("last_scraped",)}),
    )
