from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


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

    county = models.ForeignKey('locations.County', on_delete=models.CASCADE, related_name='scrape_jobs')
    job_type = models.CharField(max_length=8, choices=JOB_TYPE)
    target_date = models.DateField()
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
        return f"ScrapeJob {self.county} {self.job_type} on {self.target_date} ({self.status})"


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

