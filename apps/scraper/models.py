import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ============================================================================
# PHASE 1: CORE JOB MANAGEMENT MODELS
# ============================================================================

class ScrapingJob(models.Model):
    """Main job for managing scraping tasks"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Descriptive name for the job")
    group_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Optional label used to group related jobs",
    )
    state = models.CharField(max_length=10, default='FL', help_text="State code (e.g., 'FL')")
    county = models.CharField(max_length=150, help_text="County name")
    
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='scraping_jobs')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    rows_processed = models.IntegerField(default=0)
    rows_success = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    
    custom_params = models.JSONField(default=dict, blank=True, help_text="Custom parameters as JSON")
    is_active = models.BooleanField(default=True, help_text="Soft delete flag")
    task_id = models.CharField(max_length=255, blank=True, help_text="Thread ID or execution identifier")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Scraping Jobs"
    
    def __str__(self):
        group = f"[{self.group_name}] " if self.group_name else ""
        return f"{group}{self.name} ({self.state}/{self.county}) - {self.status}"


class JobExecutionLog(models.Model):
    """Tracks execution history of a job"""
    
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name='execution_logs')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='started')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    execution_duration = models.DurationField(null=True, blank=True, help_text="Total execution time")
    rows_processed = models.IntegerField(default=0)
    task_id = models.CharField(max_length=255, blank=True, help_text="Thread ID")
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Execution {self.job.name} - {self.status}"


class JobError(models.Model):
    """Tracks errors that occur during job execution"""
    
    ERROR_TYPE_CHOICES = [
        ('Network', 'Network Error'),
        ('Parsing', 'Parsing Error'),
        ('DataValidation', 'Data Validation Error'),
        ('System', 'System Error'),
    ]
    
    job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name='errors')
    execution_log = models.ForeignKey(JobExecutionLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='errors')
    
    error_type = models.CharField(max_length=32, choices=ERROR_TYPE_CHOICES)
    error_message = models.TextField()
    error_traceback = models.TextField(blank=True)
    
    is_retryable = models.BooleanField(default=True)
    retry_attempt = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Error {self.error_type} in {self.job.name} - Attempt {self.retry_attempt}"


class CountyScrapeURL(models.Model):
    """Stores base URLs for county scraping, one per county + job type"""

    URL_TYPE_CHOICES = [
        ('TD', 'Tax Deed'),
        ('TL', 'Tax Lien'),
        ('SS', 'Sheriff Sale'),
        ('MF', 'Mortgage Foreclosure'),
    ]

    county = models.ForeignKey('locations.County', on_delete=models.CASCADE, related_name='scrape_urls')
    state = models.ForeignKey('locations.State', on_delete=models.CASCADE, related_name='county_scrape_urls', help_text="Quick reference to state")
    url_type = models.CharField(max_length=8, choices=URL_TYPE_CHOICES, default='MF', help_text="Job type this URL is for")

    base_url = models.URLField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    notes = models.TextField(blank=True, help_text="Optional notes about this URL")

    class Meta:
        unique_together = [['county', 'url_type']]
        verbose_name_plural = "County Scrape URLs"

    def __str__(self):
        return f"{self.county} ({self.get_url_type_display()}) - {self.base_url}"


class UserJobDefaults(models.Model):
    """Stores user's default job parameters"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='job_defaults')
    
    default_state = models.ForeignKey('locations.State', on_delete=models.SET_NULL, null=True, blank=True)
    default_county = models.ForeignKey('locations.County', on_delete=models.SET_NULL, null=True, blank=True)
    
    last_start_date = models.DateField(null=True, blank=True)
    last_end_date = models.DateField(null=True, blank=True)
    last_custom_params = models.JSONField(null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        get_latest_by = 'updated_at'
        verbose_name_plural = "User Job Defaults"
    
    def __str__(self):
        return f"Defaults for {self.user.username}"


# ============================================================================
# LEGACY MODELS: ScrapeJob & ScrapeLog (Kept for backward compatibility)
# ============================================================================

class ScrapeJob(models.Model):
    JOB_STATUS = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    JOB_TYPE = [
        ('TD', 'Tax Deed'),
        ('TL', 'Tax Lien'),
        ('SS', 'Sheriff Sale'),
        ('MF', 'Mortgage Foreclosure'),
    ]

    name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Human-friendly identifier used to group related jobs",
    )
    county = models.ForeignKey('locations.County', on_delete=models.CASCADE, related_name='scrape_jobs')
    job_type = models.CharField(max_length=8, choices=JOB_TYPE)
    target_date = models.DateField(help_text="Start date for scraping")
    end_date = models.DateField(null=True, blank=True, help_text="End date (inclusive). Leave blank for single date.")
    status = models.CharField(max_length=32, choices=JOB_STATUS, default='pending')
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    prospects_created = models.PositiveIntegerField(default=0)
    prospects_updated = models.PositiveIntegerField(default=0)
    prospects_qualified = models.PositiveIntegerField(default=0)
    prospects_disqualified = models.PositiveIntegerField(default=0)
    
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        label = self.name or f"{self.county} {self.job_type}"
        return f"ScrapeJob {label} on {self.target_date} ({self.status})"


class ScrapeLog(models.Model):
    LOG_LEVEL = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    job = models.ForeignKey(ScrapeJob, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=32, choices=LOG_LEVEL)
    message = models.TextField()
    raw_html = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"[{self.level.upper()}] {self.message[:60]}"

