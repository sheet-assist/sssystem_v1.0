from django.contrib import admin
from .models import ScrapeJob, ScrapeLog


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

