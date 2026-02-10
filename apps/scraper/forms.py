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

# ============================================================================
# PROSPECT FILTER FORM: Financial Criteria Filtering
# ============================================================================

class ProspectFilterForm(forms.Form):
    """Form for filtering prospects by financial criteria"""
    
    plaintiff_max_bid_min = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Min Plaintiff Max Bid",
            "step": "1000",
        }),
        label="Min Plaintiff Max Bid"
    )
    
    plaintiff_max_bid_max = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Max Plaintiff Max Bid",
            "step": "1000",
        }),
        label="Max Plaintiff Max Bid"
    )
    
    assessed_value_min = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Min Assessed Value",
            "step": "1000",
        }),
        label="Min Assessed Value"
    )
    
    assessed_value_max = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Max Assessed Value",
            "step": "1000",
        }),
        label="Max Assessed Value"
    )
    
    final_judgment_min = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Min Final Judgment",
            "step": "1000",
        }),
        label="Min Final Judgment Amount"
    )
    
    final_judgment_max = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Max Final Judgment",
            "step": "1000",
        }),
        label="Max Final Judgment Amount"
    )
    
    sale_amount_min = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Min Sale Amount",
            "step": "1000",
        }),
        label="Min Sale Amount"
    )
    
    sale_amount_max = forms.DecimalField(
        required=False,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Max Sale Amount",
            "step": "1000",
        }),
        label="Max Sale Amount"
    )
    
    def clean(self):
        cleaned = super().clean()
        
        # Validate plaintiff_max_bid range
        plaintiff_min = cleaned.get('plaintiff_max_bid_min')
        plaintiff_max = cleaned.get('plaintiff_max_bid_max')
        if plaintiff_min and plaintiff_max and plaintiff_max < plaintiff_min:
            raise forms.ValidationError("Plaintiff Max Bid: Max value must be >= Min value.")
        
        # Validate assessed_value range
        assessed_min = cleaned.get('assessed_value_min')
        assessed_max = cleaned.get('assessed_value_max')
        if assessed_min and assessed_max and assessed_max < assessed_min:
            raise forms.ValidationError("Assessed Value: Max value must be >= Min value.")
        
        # Validate final_judgment range
        judgment_min = cleaned.get('final_judgment_min')
        judgment_max = cleaned.get('final_judgment_max')
        if judgment_min and judgment_max and judgment_max < judgment_min:
            raise forms.ValidationError("Final Judgment: Max value must be >= Min value.")
        
        # Validate sale_amount range
        sale_min = cleaned.get('sale_amount_min')
        sale_max = cleaned.get('sale_amount_max')
        if sale_min and sale_max and sale_max < sale_min:
            raise forms.ValidationError("Sale Amount: Max value must be >= Min value.")
        
        return cleaned


# ============================================================================
# COUNTY SCRAPE URL MANAGEMENT FORMS
# ============================================================================

class CountyScrapeURLForm(forms.ModelForm):
    """Form for creating and editing CountyScrapeURL records"""

    state = forms.ModelChoiceField(
        queryset=State.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_state",
        }),
        label="State"
    )

    county = forms.ModelChoiceField(
        queryset=County.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_county",
        }),
        label="County"
    )

    base_url = forms.URLField(
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://example.com/...",
        }),
        label="Base URL"
    )

    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="Active"
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Optional notes about this URL",
        }),
        label="Notes"
    )

    class Meta:
        from .models import CountyScrapeURL
        model = CountyScrapeURL
        fields = ['state', 'county', 'url_type', 'base_url', 'is_active', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate county queryset based on state if editing
        if self.instance and self.instance.pk and self.instance.state:
            self.fields['county'].queryset = County.objects.filter(
                state=self.instance.state,
                is_active=True
            )
        
        self.fields['is_active'].initial = True

