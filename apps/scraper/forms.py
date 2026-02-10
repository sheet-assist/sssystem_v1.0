from django import forms

from apps.locations.models import County

from .models import ScrapeJob


class ScrapeJobForm(forms.ModelForm):
    county = forms.ModelChoiceField(
        queryset=County.objects.filter(is_active=True).select_related("state"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    job_type = forms.ChoiceField(
        choices=ScrapeJob.JOB_TYPE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    target_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Start Date",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="End Date (optional)",
        help_text="Leave blank to scrape a single date.",
    )

    class Meta:
        model = ScrapeJob
        fields = ["county", "job_type", "target_date", "end_date"]

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("target_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after the start date.")
        return cleaned
