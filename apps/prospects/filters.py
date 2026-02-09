import django_filters
from django import forms

from .models import Prospect


class ProspectFilter(django_filters.FilterSet):
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
        for name, f in self.filters.items():
            if hasattr(f, "field") and hasattr(f.field, "widget"):
                widget = f.field.widget
                if isinstance(widget, forms.Select):
                    widget.attrs.setdefault("class", "form-select form-select-sm")
