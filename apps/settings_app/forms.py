from django import forms

from apps.locations.models import County
from apps.prospects.models import Prospect

from .models import FilterCriteria
from .models import SSRevenueSetting


class FilterCriteriaForm(forms.ModelForm):
    counties = forms.ModelMultipleChoiceField(
        queryset=County.objects.filter(is_active=True).select_related("state").order_by("state__name", "name"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select counties-select",
                "data-select-all-target": "counties",
                "size": 8,
            }
        ),
        label="Counties",
        help_text="Choose one or more counties that this rule applies to",
    )

    prospect_types = forms.MultipleChoiceField(
        choices=Prospect.PROSPECT_TYPES,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
        label="Document Types",
        help_text="Select MF/TD/etc. Leave empty for all types",
    )

    status_types = forms.MultipleChoiceField(
        choices=Prospect.AUCTION_STATUS_CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
        label="Auction Status",
    )

    class Meta:
        model = FilterCriteria
        fields = [
            "name", "prospect_types", "state", "counties",
            "plaintiff_max_bid_min", "plaintiff_max_bid_max",
            "assessed_value_min", "assessed_value_max",
            "final_judgment_min", "final_judgment_max",
            "sale_amount_min", "sale_amount_max",
            "surplus_amount_min", "surplus_amount_max",
            "sold_to",
            "min_date", "max_date", "status_types", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.Select(attrs={"class": "form-select"}),
            
            # Financial Criteria
            "plaintiff_max_bid_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000", 
                "placeholder": "Min plaintiff bid"}),
            "plaintiff_max_bid_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Max plaintiff bid"}),
            "assessed_value_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Min assessed value"}),
            "assessed_value_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Max assessed value"}),
            "final_judgment_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Min final judgment"}),
            "final_judgment_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Max final judgment"}),
            "sale_amount_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Min sale amount"}),
            "sale_amount_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Max sale amount"}),
            "surplus_amount_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Min surplus amount"}),
            "surplus_amount_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "1000",
                "placeholder": "Max surplus amount"}),
            "sold_to": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Exact Sold To match",
            }),
            
            "min_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "max_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["prospect_types"].initial = self.instance.prospect_types or []
            self.fields["counties"].initial = self.instance.counties.all()
            self.fields["status_types"].initial = self.instance.status_types
            self.fields["min_date"].initial = self.instance.min_date
            self.fields["max_date"].initial = self.instance.max_date
        else:
            self.fields["status_types"].initial = []
            self.fields["prospect_types"].initial = []
            self.fields["counties"].initial = []
            self.fields["min_date"].initial = None
            self.fields["max_date"].initial = None

    def clean_prospect_types(self):
        return self.cleaned_data.get("prospect_types") or []

    def clean_status_types(self):
        return self.cleaned_data.get("status_types") or []
    
    def clean(self):
        cleaned = super().clean()
        
        # Validate plaintiff_max_bid range
        plaintiff_min = cleaned.get('plaintiff_max_bid_min')
        plaintiff_max = cleaned.get('plaintiff_max_bid_max')
        if plaintiff_min and plaintiff_max and plaintiff_max < plaintiff_min:
            raise forms.ValidationError("Plaintiff Max Bid: Max must be >= Min.")
        
        # Validate assessed_value range
        assessed_min = cleaned.get('assessed_value_min')
        assessed_max = cleaned.get('assessed_value_max')
        if assessed_min and assessed_max and assessed_max < assessed_min:
            raise forms.ValidationError("Assessed Value: Max must be >= Min.")
        
        # Validate final_judgment range
        judgment_min = cleaned.get('final_judgment_min')
        judgment_max = cleaned.get('final_judgment_max')
        if judgment_min and judgment_max and judgment_max < judgment_min:
            raise forms.ValidationError("Final Judgment: Max must be >= Min.")
        
        # Validate sale_amount range
        sale_min = cleaned.get('sale_amount_min')
        sale_max = cleaned.get('sale_amount_max')
        if sale_min and sale_max and sale_max < sale_min:
            raise forms.ValidationError("Sale Amount: Max must be >= Min.")

        surplus_min = cleaned.get('surplus_amount_min')
        surplus_max = cleaned.get('surplus_amount_max')
        if surplus_min and surplus_max and surplus_max < surplus_min:
            raise forms.ValidationError("Surplus Amount: Max must be >= Min.")

        start_date = cleaned.get("min_date")
        end_date = cleaned.get("max_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("Auction Date: End must be on or after Start.")
        
        return cleaned


class SSRevenueTierForm(forms.Form):
    tier_percent = forms.ChoiceField(
        choices=SSRevenueSetting.TIER_CHOICES,
        widget=forms.RadioSelect,
        initial="15",
        label="SS Revenue Tier",
    )
    ars_tier_percent = forms.ChoiceField(
        choices=SSRevenueSetting.ARS_TIER_CHOICES,
        widget=forms.RadioSelect,
        initial="5",
        label="ARS Tiers Payout",
    )
