from django.contrib import admin

from .models import Case, CaseActionLog, CaseFollowUp, CaseNote


class CaseNoteInline(admin.TabularInline):
    model = CaseNote
    extra = 0
    readonly_fields = ("author", "created_at")


class CaseFollowUpInline(admin.TabularInline):
    model = CaseFollowUp
    extra = 0


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("case_number", "case_type", "county", "status", "assigned_to", "created_at")
    list_filter = ("status", "case_type", "county")
    search_fields = ("case_number", "parcel_id", "property_address")
    inlines = [CaseNoteInline, CaseFollowUpInline]


@admin.register(CaseNote)
class CaseNoteAdmin(admin.ModelAdmin):
    list_display = ("case", "author", "created_at")


@admin.register(CaseFollowUp)
class CaseFollowUpAdmin(admin.ModelAdmin):
    list_display = ("case", "assigned_to", "due_date", "is_completed")
    list_filter = ("is_completed",)


@admin.register(CaseActionLog)
class CaseActionLogAdmin(admin.ModelAdmin):
    list_display = ("case", "action_type", "user", "created_at")
    list_filter = ("action_type",)
