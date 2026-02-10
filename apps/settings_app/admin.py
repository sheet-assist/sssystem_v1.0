from django.contrib import admin

from .models import FilterCriteria


@admin.register(FilterCriteria)
class FilterCriteriaAdmin(admin.ModelAdmin):
    list_display = ("name", "prospect_type", "state", "county", "is_active")
    list_filter = ("prospect_type", "is_active", "state")
    search_fields = ("name",)
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "prospect_type", "state", "county")
        }),
        ("Financial Criteria", {
            "fields": (
                ("plaintiff_max_bid_min", "plaintiff_max_bid_max"),
                ("assessed_value_min", "assessed_value_max"),
                ("final_judgment_min", "final_judgment_max"),
                ("sale_amount_min", "sale_amount_max"),
            ),
            "description": "Set min/max ranges for prospect financial values. Leave blank to skip filter."
        }),
        ("Other Criteria", {
            "fields": ("min_date", "status_types", "auction_types")
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )
