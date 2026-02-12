from django.contrib import admin

from .models import FilterCriteria


@admin.register(FilterCriteria)
class FilterCriteriaAdmin(admin.ModelAdmin):
    list_display = ("name", "display_types", "state", "display_counties", "is_active")
    list_filter = ("is_active", "state")
    search_fields = ("name",)
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "prospect_types", "state", "counties")
        }),
        ("Financial Criteria", {
            "fields": (
                ("plaintiff_max_bid_min", "plaintiff_max_bid_max"),
                ("assessed_value_min", "assessed_value_max"),
                ("final_judgment_min", "final_judgment_max"),
                ("sale_amount_min", "sale_amount_max"),
                ("surplus_amount_min", "surplus_amount_max"),
                "sold_to",
            ),
            "description": "Set min/max ranges for prospect financial values. Leave blank to skip filter."
        }),
        ("Other Criteria", {
            "fields": (("min_date", "max_date"), "status_types")
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )

    def display_types(self, obj):
        types = obj.prospect_types or ([obj.prospect_type] if obj.prospect_type else [])
        return ", ".join(types) if types else "All"

    display_types.short_description = "Types"

    def display_counties(self, obj):
        county_list = list(obj.counties.values_list("name", flat=True))
        if county_list:
            return ", ".join(county_list[:2]) + ("…" if len(county_list) > 2 else "")
        if obj.county:
            return obj.county.name
        return "—"

    display_counties.short_description = "Counties"
