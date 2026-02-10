from django import forms
from django.contrib.auth import get_user_model

from .models import Case, CaseFollowUp, CaseNote

User = get_user_model()


class ConvertToCaseForm(forms.Form):
    contract_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    contract_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class CaseNoteForm(forms.ModelForm):
    class Meta:
        model = CaseNote
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class CaseFollowUpForm(forms.ModelForm):
    class Meta:
        model = CaseFollowUp
        fields = ["due_date", "description", "assigned_to"]
        widgets = {
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
        }


class CaseStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=Case.CASE_STATUS,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
