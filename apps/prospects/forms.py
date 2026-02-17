from django import forms
from django.contrib.auth import get_user_model

from apps.locations.models import State, County
from .models import Prospect, ProspectNote

User = get_user_model()

MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB


class CSVUploadForm(forms.Form):
    state = forms.ModelChoiceField(
        queryset=State.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_state"}),
        empty_label="-- Choose a state --",
    )
    county = forms.ModelChoiceField(
        queryset=County.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_county"}),
        empty_label="-- Choose a county --",
    )
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv"}),
        help_text="Upload a .csv file (max 5 MB).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "state" in self.data:
            try:
                state_id = int(self.data.get("state"))
                self.fields["county"].queryset = County.objects.filter(
                    state_id=state_id, is_active=True
                )
            except (ValueError, TypeError):
                pass

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Only .csv files are accepted.")
        if f.size > MAX_CSV_SIZE:
            raise forms.ValidationError("File size must be under 5 MB.")
        return f


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
