from django import forms

from .models import FilterCriteria


class FilterCriteriaForm(forms.ModelForm):
    class Meta:
        model = FilterCriteria
        fields = [
            "name", "prospect_type", "state", "county",
            "min_surplus_amount", "min_date",
            "status_types", "auction_types", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "prospect_type": forms.Select(attrs={"class": "form-select"}),
            "state": forms.Select(attrs={"class": "form-select"}),
            "county": forms.Select(attrs={"class": "form-select"}),
            "min_surplus_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "min_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status_types": forms.Textarea(attrs={"class": "form-control", "rows": 2,
                                                   "placeholder": '["Live", "Upcoming"]'}),
            "auction_types": forms.Textarea(attrs={"class": "form-control", "rows": 2,
                                                    "placeholder": '["Tax Deed"]'}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
