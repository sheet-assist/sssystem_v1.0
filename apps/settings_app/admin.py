from django.contrib import admin

from .models import FilterCriteria


@admin.register(FilterCriteria)
class FilterCriteriaAdmin(admin.ModelAdmin):
    list_display = ("name", "prospect_type", "state", "county", "min_surplus_amount", "is_active")
    list_filter = ("prospect_type", "is_active", "state")
    search_fields = ("name",)
