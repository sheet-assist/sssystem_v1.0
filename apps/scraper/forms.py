from django import forms
from django.contrib.auth.models import User
from datetime import date, timedelta

from apps.locations.models import County, State
from .models import ScrapeJob, ScrapingJob, CountyScrapeURL
from .services import JobDateService, UserDefaultsService


# ============================================================================
# CUSTOM FIELDS AND WIDGETS
# ============================================================================

class CountyWithURLChoiceField(forms.ModelMultipleChoiceField):
    """Custom field to display county name with active URL if available"""
    
    def __init__(self, *args, job_type=None, **kwargs):
        self.job_type = job_type
        super().__init__(*args, **kwargs)
    
    def label_from_instance(self, obj):
        """Display county name with active URL if available"""
        label = obj.name
        
        # Try to get active URL for this county and job type
        if self.job_type:
            try:
                url_obj = CountyScrapeURL.objects.get(
                    county=obj,
                    url_type=self.job_type,
                    is_active=True
                )
                if url_obj.base_url:
                    label = f"{obj.name} - {url_obj.base_url}"
            except CountyScrapeURL.DoesNotExist:
                pass
        
        return label


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
    group_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Optional group label (e.g., Miami Batch A)",
        }),
        label="Group Name",
        help_text="Use to group related jobs on the job list",
    )
    
    class Meta:
        model = ScrapingJob
        fields = ['name', 'group_name', 'start_date', 'end_date']
    
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
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g., Florida TD Batch 2026-03-01",
        }),
        label="Job Name",
        help_text="Used to group multiple county runs into a single batch",
    )
    state = forms.ModelChoiceField(
        queryset=State.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_state",
        }),
        label="State",
    )
    counties = forms.ModelMultipleChoiceField(
        queryset=County.objects.none(),
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "id": "id_counties",
            "size": "12",
        }),
        label="Counties",
        help_text="County names show active URL if available. Use Ctrl/Command + click for multi-select.",
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
        fields = ["name", "job_type", "target_date", "end_date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Always work with fresh queryset copies
        self.fields["state"].queryset = State.objects.filter(is_active=True).order_by("name")
        
        # Get the job_type to pass to counties field
        job_type = self.data.get("job_type") or self.initial.get("job_type")

        state_value = self.data.get("state") or self.initial.get("state")
        state_obj = None

        # If editing an instance, load the state from the instance's county
        if self.instance.pk and not state_value:
            if hasattr(self.instance, "county") and self.instance.county:
                state_obj = self.instance.county.state
                # Set the initial value for the state field
                self.fields["state"].initial = state_obj
        else:
            if isinstance(state_value, State):
                state_obj = state_value
            elif state_value:
                try:
                    state_obj = State.objects.get(pk=state_value)
                except (State.DoesNotExist, ValueError):
                    state_obj = None

        if state_obj is None and hasattr(self.instance, "county") and self.instance.pk:
            state_obj = self.instance.county.state

        if state_obj:
            # Use custom field with job_type to display URLs
            county_queryset = County.objects.filter(
                is_active=True,
                state=state_obj,
            ).order_by("name")
            
            # Replace the counties field with our custom field
            self.fields["counties"] = CountyWithURLChoiceField(
                queryset=county_queryset,
                job_type=job_type,
                widget=forms.SelectMultiple(attrs={
                    "class": "form-select",
                    "id": "id_counties",
                    "size": "12",
                }),
                label="Counties",
                help_text="County names show active URL if available. Use Ctrl/Command + click for multi-select.",
            )
            
            # If editing, pre-populate the counties field with the current county
            if self.instance.pk and not self.data.get("counties"):
                if self.instance.county:
                    self.fields["counties"].initial = [self.instance.county]
            
            self.fields["counties"].widget.attrs.pop("disabled", None)
        else:
            self.fields["counties"].queryset = County.objects.none()
            self.fields["counties"].widget.attrs["disabled"] = "disabled"

    def clean(self):
        cleaned = super().clean()
        state = cleaned.get("state")
        counties = cleaned.get("counties")
        start = cleaned.get("target_date")
        end = cleaned.get("end_date")

        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after the start date.")

        if not counties:
            self.add_error("counties", "Select at least one county.")
        elif state:
            invalid = [county for county in counties if county.state_id != state.id]
            if invalid:
                self.add_error(
                    "counties",
                    "All selected counties must belong to the chosen state.",
                )

        return cleaned

    def save_multiple(self, *, triggered_by=None):
        """Create a ScrapeJob per selected county."""
        if not self.is_valid():
            raise ValueError("Cannot save jobs from an invalid form.")

        jobs = []
        job_data = {
            "name": self.cleaned_data["name"],
            "job_type": self.cleaned_data["job_type"],
            "target_date": self.cleaned_data["target_date"],
            "end_date": self.cleaned_data.get("end_date"),
            "status": "pending",
        }

        for county in self.cleaned_data["counties"]:
            job = ScrapeJob(
                county=county,
                **job_data,
            )
            if triggered_by:
                job.triggered_by = triggered_by
            job.save()
            jobs.append(job)

        return jobs

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

    ac = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="AC (Assessment Certificate) Enabled"
    )

    ac_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://example.com/ac/...",
        }),
        label="AC URL"
    )

    tdm = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="TDM (Tax Deed Market) Enabled"
    )

    tdm_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://example.com/tdm/...",
        }),
        label="TDM URL"
    )

    class Meta:
        from .models import CountyScrapeURL
        model = CountyScrapeURL
        fields = ['state', 'county', 'url_type', 'base_url', 'is_active', 'ac', 'ac_url', 'tdm', 'tdm_url', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate county queryset based on state if editing
        if self.instance and self.instance.pk and self.instance.state:
            self.fields['county'].queryset = County.objects.filter(
                state=self.instance.state,
                is_active=True
            )
        
        self.fields['is_active'].initial = True

