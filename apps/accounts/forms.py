from django import forms
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile and role"""
    
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "First Name",
        }),
        label="First Name"
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Last Name",
        }),
        label="Last Name"
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Email",
        }),
        label="Email"
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="Active"
    )
    
    class Meta:
        model = UserProfile
        fields = ['role', 'phone']
        widgets = {
            'role': forms.Select(attrs={
                "class": "form-select",
            }),
            'phone': forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Phone",
            }),
        }
        labels = {
            'role': 'Role',
            'phone': 'Phone',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate user fields if instance exists
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
            self.fields['is_active'].initial = self.instance.user.is_active
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Save user fields
        if instance.user:
            instance.user.first_name = self.cleaned_data.get('first_name', '')
            instance.user.last_name = self.cleaned_data.get('last_name', '')
            instance.user.email = self.cleaned_data.get('email', '')
            instance.user.is_active = self.cleaned_data.get('is_active', True)
            instance.user.save()
        
        if commit:
            instance.save()
        
        return instance
