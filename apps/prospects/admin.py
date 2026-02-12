from django.contrib import admin

from .models import (
    Prospect,
    ProspectActionLog,
    ProspectEmail,
    ProspectNote,
    ProspectRuleNote,
)


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = ("prospect_type", "case_number", "county", "qualification_status", "workflow_status", "assigned_to", "auction_date")
    list_filter = ("prospect_type", "qualification_status", "workflow_status", "county__state")
    search_fields = ("case_number", "parcel_id", "plaintiff_name", "defendant_name", "property_address")
    raw_id_fields = ("assigned_to", "assigned_by")


@admin.register(ProspectNote)
class ProspectNoteAdmin(admin.ModelAdmin):
    list_display = ("prospect", "author", "created_at")


@admin.register(ProspectActionLog)
class ProspectActionLogAdmin(admin.ModelAdmin):
    list_display = ("prospect", "action_type", "user", "created_at")
    list_filter = ("action_type",)


@admin.register(ProspectEmail)
class ProspectEmailAdmin(admin.ModelAdmin):
    list_display = ("prospect", "sender", "subject", "sent_at")


@admin.register(ProspectRuleNote)
class ProspectRuleNoteAdmin(admin.ModelAdmin):
    list_display = ("prospect", "rule_name", "decision", "source", "created_by", "created_at")
    list_filter = ("source", "decision")
    search_fields = ("prospect__case_number", "note", "rule_name")
