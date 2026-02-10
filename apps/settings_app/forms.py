from django import forms

from .models import FilterCriteria


class FilterCriteriaForm(forms.ModelForm):
    class Meta:
        model = FilterCriteria
        fields = [
            "name", "prospect_type", "state", "county",
            "plaintiff_max_bid_min", "plaintiff_max_bid_max",
            "assessed_value_min", "assessed_value_max",
            "final_judgment_min", "final_judgment_max",
            "sale_amount_min", "sale_amount_max",
            "min_date", "status_types", "auction_types", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "prospect_type": forms.Select(attrs={"class": "form-select"}),
            "state": forms.Select(attrs={"class": "form-select"}),
            "county": forms.Select(attrs={"class": "form-select"}),
            
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
            
            "min_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status_types": forms.Textarea(attrs={"class": "form-control", "rows": 2,
                                                   "placeholder": '["Live", "Upcoming"]'}),
            "auction_types": forms.Textarea(attrs={"class": "form-control", "rows": 2,
                                                    "placeholder": '["Tax Deed"]'}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    
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
        
        return cleaned
