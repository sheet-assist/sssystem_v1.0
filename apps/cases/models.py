from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Case(models.Model):
    CASE_TYPE_CHOICES = [
        ("TD", "Tax Deed"),
        ("TL", "Tax Lien"),
        ("SS", "Sheriff Sale"),
        ("MF", "Mortgage Foreclosure"),
    ]

    CASE_STATUS = [
        ("active", "Active"),
        ("monitoring", "Monitoring"),
        ("follow_up", "Follow Up"),
        ("closed_won", "Closed Won"),
        ("closed_lost", "Closed Lost"),
    ]

    prospect = models.OneToOneField("prospects.Prospect", on_delete=models.CASCADE, related_name="case")
    case_type = models.CharField(max_length=8, choices=CASE_TYPE_CHOICES)
    county = models.ForeignKey("locations.County", on_delete=models.CASCADE, related_name="cases")
    status = models.CharField(max_length=32, choices=CASE_STATUS, default="active")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_cases")

    property_address = models.CharField(max_length=400, blank=True, default="")
    case_number = models.CharField(max_length=200, blank=True, default="")
    parcel_id = models.CharField(max_length=200, blank=True, default="")

    contract_date = models.DateField(null=True, blank=True)
    contract_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Case {self.case_number or self.pk} ({self.case_type})"


class CaseNote(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on Case {self.case.pk} by {self.author}"


class CaseFollowUp(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="followups")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField()
    description = models.TextField()
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"Follow-up for Case {self.case.pk} due {self.due_date}"


class CaseActionLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="action_logs")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=64)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type} on Case {self.case.pk}"


def log_case_action(case, user, action_type, description="", metadata=None):
    return CaseActionLog.objects.create(
        case=case, user=user, action_type=action_type,
        description=description, metadata=metadata or {},
    )
