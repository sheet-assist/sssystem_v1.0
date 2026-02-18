import django_filters
from django import forms

from apps.locations.models import County, State
from apps.settings_app.models import SSRevenueSetting
from .models import Prospect


def get_surplus_threshold_choices():
    """Generate surplus amount filter choices from SSRevenueSetting."""
    setting = SSRevenueSetting.get_solo()

    def _as_k_label(value):
        numeric_value = int(value)
        if numeric_value % 1000 == 0:
            return f"{numeric_value // 1000}K"
        return f"${numeric_value:,.0f}"

    return [
        ("1", f"Less than {_as_k_label(setting.surplus_threshold_1)}"),
        ("2", f"Less than {_as_k_label(setting.surplus_threshold_2)}"),
        ("3", f"Less than {_as_k_label(setting.surplus_threshold_3)}"),
    ]


class ProspectFilter(django_filters.FilterSet):
    qualification_status = django_filters.ChoiceFilter(
        field_name="qualification_status",
        choices=Prospect.QUALIFICATION_STATUS,
        label="Qualified Status",
        empty_label="All",
    )
    workflow_status = django_filters.ChoiceFilter(
        field_name="workflow_status",
        choices=Prospect.WORKFLOW_STATUS,
        label="Status",
        empty_label="All",
    )
    state = django_filters.ModelChoiceFilter(
        field_name="county__state",
        queryset=State.objects.filter(is_active=True).order_by("name"),
        label="State",
        empty_label="All States",
    )
    county = django_filters.ModelChoiceFilter(
        field_name="county",
        queryset=County.objects.filter(is_active=True).select_related("state").order_by("state__name", "name"),
        label="County",
        empty_label="All Counties",
    )
    surplus_amount_range = django_filters.ChoiceFilter(
        field_name="surplus_amount",
        method="filter_surplus_amount",
        choices=get_surplus_threshold_choices,
        label="Surplus Amount",
        empty_label="All",
    )
    auction_date_from = django_filters.DateFilter(
        field_name="auction_date", lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
        label="From",
    )
    auction_date_to = django_filters.DateFilter(
        field_name="auction_date", lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
        label="To",
    )

    class Meta:
        model = Prospect
        fields = [
            "qualification_status",
            "workflow_status",
            "auction_status",
            "assigned_to",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected_state = self.data.get("state") if hasattr(self, "data") else None
        if selected_state:
            self.filters["county"].queryset = County.objects.filter(
                is_active=True,
                state_id=selected_state,
            ).order_by("name")
        for name, f in self.filters.items():
            if hasattr(f, "field") and hasattr(f.field, "widget"):
                widget = f.field.widget
                if isinstance(widget, forms.Select):
                    widget.attrs.setdefault("class", "form-select form-select-sm")    
    def filter_surplus_amount(self, queryset, name, value):
        """Filter prospects by surplus amount ranges based on settings."""
        if not value:
            return queryset
        
        setting = SSRevenueSetting.get_solo()
        
        if value == "1":
            return queryset.filter(surplus_amount__lt=setting.surplus_threshold_1)
        elif value == "2":
            return queryset.filter(surplus_amount__lt=setting.surplus_threshold_2)
        elif value == "3":
            return queryset.filter(surplus_amount__lt=setting.surplus_threshold_3)
        
        return queryset
