from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
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
        fields = ['role', 'phone', 'can_manage_finance_settings']
        widgets = {
            'role': forms.Select(attrs={
                "class": "form-select",
            }),
            'phone': forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Phone",
            }),
            'can_manage_finance_settings': forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }
        labels = {
            'role': 'Role',
            'phone': 'Phone',
            'can_manage_finance_settings': 'Can Manage Finance Settings',
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


class UserCreateForm(UserCreationForm):
    """Form for creating a user and initializing profile settings."""

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "First Name",
        }),
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Last Name",
        }),
        label="Last Name",
    )

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Email",
        }),
        label="Email",
    )

    is_active = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="Active",
    )

    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        initial=UserProfile.ROLE_PROSPECTS_ONLY,
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        label="Role",
    )

    phone = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Phone",
        }),
        label="Phone",
    )

    can_manage_finance_settings = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="Can Manage Finance Settings",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
            "is_active",
            "role",
            "phone",
            "can_manage_finance_settings",
        )
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Username",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Username",
        })
        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Password",
        })
        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirm Password",
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email", "")
        user.is_active = self.cleaned_data.get("is_active", True)
        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data.get("role", UserProfile.ROLE_PROSPECTS_ONLY)
            profile.phone = self.cleaned_data.get("phone", "")
            profile.can_manage_finance_settings = self.cleaned_data.get("can_manage_finance_settings", False)
            profile.save()
        return user
