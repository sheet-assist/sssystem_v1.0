import django_filters
from django import forms

from apps.locations.models import County, State
from .models import Prospect


class ProspectFilter(django_filters.FilterSet):
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
