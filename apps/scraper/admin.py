from django.contrib import admin
from .models import (
    ScrapingJob, JobExecutionLog, JobError, CountyScrapeURL, UserJobDefaults,
    ScrapeJob, ScrapeLog
)


# ============================================================================
# PHASE 1: ADMIN INTERFACE FOR CORE JOB MANAGEMENT
# ============================================================================

@admin.register(ScrapingJob)
class ScrapingJobAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'county', 'status', 'rows_success', 'created_at', 'created_by')
    list_filter = ('status', 'created_at', 'state', 'created_by')
    search_fields = ('name', 'county', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at', 'task_id', 'id')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'name', 'state', 'county', 'status', 'created_by')
        }),
        ('Date Range', {
            'fields': ('start_date', 'end_date')
        }),
        ('Execution Metrics', {
            'fields': ('rows_processed', 'rows_success', 'rows_failed', 'task_id')
        }),
        ('Parameters', {
            'fields': ('custom_params',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly.extend(['state', 'county', 'start_date', 'end_date'])
        return readonly


@admin.register(JobExecutionLog)
class JobExecutionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'status', 'started_at', 'completed_at', 'rows_processed')
    list_filter = ('status', 'started_at', 'job__state')
    search_fields = ('job__name', 'task_id')
    readonly_fields = ('started_at', 'id')
    
    fieldsets = (
        ('Job Info', {
            'fields': ('id', 'job', 'task_id')
        }),
        ('Execution Status', {
            'fields': ('status', 'started_at', 'completed_at', 'execution_duration')
        }),
        ('Results', {
            'fields': ('rows_processed',)
        }),
    )


@admin.register(JobError)
class JobErrorAdmin(admin.ModelAdmin):
    list_display = ('error_type', 'job', 'is_retryable', 'retry_attempt', 'created_at')
    list_filter = ('error_type', 'is_retryable', 'retry_attempt', 'created_at')
    search_fields = ('job__name', 'error_message')
    readonly_fields = ('created_at', 'id')
    
    fieldsets = (
        ('Error Info', {
            'fields': ('id', 'job', 'execution_log', 'error_type')
        }),
        ('Error Details', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('wide',)
        }),
        ('Retry Info', {
            'fields': ('is_retryable', 'retry_attempt', 'created_at')
        }),
    )


@admin.register(CountyScrapeURL)
class CountyScrapeURLAdmin(admin.ModelAdmin):
    list_display = ('county', 'state', 'url_type', 'base_url', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('state', 'url_type', 'is_active', 'updated_at')
    search_fields = ('county__name', 'state__name')
    readonly_fields = ('created_at', 'updated_at', 'id')

    fieldsets = (
        ('County Info', {
            'fields': ('id', 'county', 'state', 'url_type')
        }),
        ('URL Configuration', {
            'fields': ('base_url', 'is_active')
        }),
        ('Audit Trail', {
            'fields': ('updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserJobDefaults)
class UserJobDefaultsAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_state', 'default_county', 'updated_at')
    list_filter = ('default_state', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('updated_at', 'id')
    
    fieldsets = (
        ('User Info', {
            'fields': ('id', 'user')
        }),
        ('Defaults', {
            'fields': ('default_state', 'default_county')
        }),
        ('Last Used', {
            'fields': ('last_start_date', 'last_end_date', 'last_custom_params'),
            'classes': ('collapse',)
        }),
        ('Updated', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )


# ============================================================================
# LEGACY ADMIN: ScrapeJob & ScrapeLog (Kept for backward compatibility)
# ============================================================================

@admin.register(ScrapeJob)
class ScrapeJobAdmin(admin.ModelAdmin):
    list_display = ('county', 'job_type', 'target_date', 'status', 'prospects_created', 'created_at')
    list_filter = ('status', 'job_type', 'created_at')
    search_fields = ('county__name',)
    readonly_fields = ('created_at', 'started_at', 'completed_at')


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = ('job', 'level', 'message', 'created_at')
    list_filter = ('level', 'job__county')
    search_fields = ('message',)
    readonly_fields = ('created_at',)

