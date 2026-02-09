from django import forms
from django.contrib.auth import get_user_model

from .models import Prospect, ProspectNote

User = get_user_model()


class AssignProspectForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class ProspectNoteForm(forms.ModelForm):
    class Meta:
        model = ProspectNote
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class WorkflowTransitionForm(forms.Form):
    workflow_status = forms.ChoiceField(
        choices=Prospect.WORKFLOW_STATUS,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class ResearchForm(forms.Form):
    lien_check_done = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    lien_check_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
    surplus_verified = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    documents_verified = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    skip_trace_done = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    owner_contact_info = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
