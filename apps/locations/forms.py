from django import forms
from .models import County


class CountyConfigForm(forms.ModelForm):
    class Meta:
        model = County
        fields = [
            'is_active',
            'available_prospect_types',
            'platform',
            'uses_realtdm',
            'uses_auction_calendar',
            'auction_calendar_url',
            'realtdm_url',
            'foreclosure_url',
            'taxdeed_url',
        ]
        widgets = {
            'available_prospect_types': forms.TextInput(attrs={'placeholder': "e.g. ['TD']"}),
        }
