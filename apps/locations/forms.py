from django import forms
from .models import County, State


class CountyConfigForm(forms.ModelForm):
    class Meta:
        model = County
        fields = [
            'is_active',
            'platform',
            'auction_calendar_url',
            'realtdm_url',
        ]


class CountyForm(forms.ModelForm):
    """Form for creating and editing counties"""
    class Meta:
        model = County
        fields = [
            'state',
            'name',
            'slug',
            'fips_code',
            'is_active',
            'platform',
            'auction_calendar_url',
            'realtdm_url',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'fips_code': forms.TextInput(attrs={'class': 'form-control'}),
            'auction_calendar_url': forms.URLInput(attrs={'class': 'form-control'}),
            'realtdm_url': forms.URLInput(attrs={'class': 'form-control'}),
        }

