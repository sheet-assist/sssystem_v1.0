from django import forms
from django.contrib.auth.models import User
from datetime import date, timedelta

from apps.locations.models import County, State

from .models import ScrapeJob, ScrapingJob
from .services import JobDateService, UserDefaultsService


# ============================================================================
# PHASE 3: ENHANCED JOB CREATION FORM WITH DYNAMIC DATES
# ============================================================================

class JobCreationForm(forms.ModelForm):
    """Form for creating a new ScrapingJob with dynamic date handling"""
    
    state = forms.ModelChoiceField(
        queryset=State.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_state",
            "data-toggle": "state-change",
        }),
        label="State"
    )
    
    county = forms.ModelChoiceField(
        queryset=County.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_county",
            "data-toggle": "county-select",
        }),
        label="County (Optional)"
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
            "id": "id_start_date",
        }),
        label="Start Date",
        help_text="Beginning date for scraping",
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
            "id": "id_end_date",
        }),
        label="End Date",
        help_text="End date for scraping (inclusive)",
    )
    
    date_preset = forms.ChoiceField(
        choices=[
            ('custom', 'Custom Date Range'),
            ('today', 'Today Only'),
            ('this_week', 'This Week (Today + 7 days)'),
            ('this_month', 'This Month (Today + 30 days)'),
            ('last_7_days', 'Last 7 Days'),
            ('last_30_days', 'Last 30 Days'),
        ],
        required=False,
        initial='this_week',
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_date_preset",
            "data-toggle": "date-preset",
        }),
        label="Quick Date Selection"
    )
    
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g., Miami-Dade Auctions February 2026",
        }),
        label="Job Name",
        help_text="Descriptive name for this job",
    )
    
    class Meta:
        model = ScrapingJob
        fields = ['name', 'start_date', 'end_date']
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        # Get user's last used defaults if available
        if user:
            defaults = UserDefaultsService.get_or_create_defaults(user)
            
            if defaults.default_state:
                self.fields['state'].initial = defaults.default_state
            
            if defaults.default_county:
                self.fields['county'].queryset = County.objects.filter(
                    is_active=True,
                    state=defaults.default_state
                )
                self.fields['county'].initial = defaults.default_county
            
            # Set initial dates
            if defaults.last_start_date and defaults.last_end_date:
                self.fields['start_date'].initial = defaults.last_start_date
                self.fields['end_date'].initial = defaults.last_end_date
            else:
                # Use suggested range (today + 7 days)
                today, end = JobDateService.get_suggested_date_range(7)
                self.fields['start_date'].initial = today
                self.fields['end_date'].initial = end
                self.fields['date_preset'].initial = 'this_week'
        else:
            # Default to today + 7 days
            today, end = JobDateService.get_suggested_date_range(7)
            self.fields['start_date'].initial = today
            self.fields['end_date'].initial = end
    
    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError("End date must be on or after the start date.")
            
            # Check range doesn't exceed reasonable limit (1 year)
            days_diff = (end_date - start_date).days
            if days_diff > 365:
                raise forms.ValidationError("Date range cannot exceed 365 days.")
        
        return cleaned
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Get state from form
        state_obj = self.cleaned_data.get('state')
        if state_obj:
            instance.state = state_obj.abbreviation
        
        # Get county name if selected
        county_obj = self.cleaned_data.get('county')
        if county_obj:
            instance.county = county_obj.name
        
        if commit:
            instance.save()
            
            # Save user defaults if user provided
            if self.user:
                UserDefaultsService.update_defaults(
                    self.user,
                    state=state_obj,
                    county=county_obj,
                    start_date=instance.start_date,
                    end_date=instance.end_date,
                )
        
        return instance


# ============================================================================
# PHASE 3: ADVANCED FILTERING FORM
# ============================================================================

class JobFilterForm(forms.Form):
    """Form for advanced filtering of ScrapingJob list"""
    
    STATUS_CHOICES = [
        ('', 'All Statuses'),
    ] + ScrapingJob.STATUS_CHOICES
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Status"
    )
    
    date_range_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
        }),
        label="Created After"
    )
    
    date_range_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
        }),
        label="Created Before"
    )
    
    state = forms.ModelChoiceField(
        queryset=State.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="State"
    )
    
    county = forms.ModelChoiceField(
        queryset=County.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="County"
    )
    
    search = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Search job names...",
        }),
        label="Search"
    )
    
    has_errors = forms.NullBooleanField(
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}, choices=[
            ('', 'All Jobs'),
            ('true', 'With Errors'),
            ('false', 'Without Errors'),
        ]),
        label="Error Status"
    )
    
    sort = forms.ChoiceField(
        choices=[
            ('-created_at', 'Newest First'),
            ('created_at', 'Oldest First'),
            ('-updated_at', 'Recently Updated'),
            ('name', 'Name A-Z'),
            ('-rows_processed', 'Most Rows Processed'),
        ],
        required=False,
        initial='-created_at',
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Sort By"
    )
    
    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('date_range_start')
        end = cleaned.get('date_range_end')
        
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after the start date.")
        
        return cleaned


# ============================================================================
# LEGACY FORMS: ScrapeJobForm (Kept for backward compatibility)
# ============================================================================

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
