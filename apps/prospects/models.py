from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Prospect(models.Model):
    PROSPECT_TYPES = [
        ("TD", "Tax Deed"),
        ("TL", "Tax Lien"),
        ("SS", "Sheriff Sale"),
        ("MF", "Mortgage Foreclosure"),
    ]

    AUCTION_STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("cancelled", "Cancelled"),
        ("sold_third_party", "Sold Third Party"),
        ("sold_plaintiff", "Sold Plaintiff"),
        ("postponed", "Postponed"),
        ("struck_off", "Struck Off"),
    ]

    QUALIFICATION_STATUS = [
        ("pending", "Pending"),
        ("qualified", "Qualified"),
        ("disqualified", "Disqualified"),
    ]

    WORKFLOW_STATUS = [
        ("new", "New"),
        ("assigned", "Assigned"),
        ("researching", "Researching"),
        ("skip_tracing", "Skip Tracing"),
        ("contacting", "Contacting"),
        ("contract_sent", "Contract Sent"),
        ("converted", "Converted"),
        ("dead", "Dead"),
    ]

    # Identity
    prospect_type = models.CharField(max_length=8, choices=PROSPECT_TYPES)
    auction_item_number = models.CharField(max_length=100, blank=True, default="")
    case_number = models.CharField(max_length=200)
    case_style = models.CharField(max_length=255, blank=True, default="")

    # Location
    county = models.ForeignKey("locations.County", on_delete=models.CASCADE, related_name="prospects")
    property_address = models.CharField(max_length=400, blank=True, default="")
    city = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(max_length=50, blank=True, default="")
    zip_code = models.CharField(max_length=20, blank=True, default="")
    parcel_id = models.CharField(max_length=200, blank=True, default="")

    # Financial
    final_judgment_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opening_bid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    plaintiff_max_bid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    assessed_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    surplus_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sale_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sold_to = models.CharField(max_length=255, blank=True, default="")

    # Schedule
    auction_type = models.CharField(max_length=100, blank=True, default="")
    auction_date = models.DateField(null=True, blank=True)
    auction_time = models.TimeField(null=True, blank=True)
    auction_status = models.CharField(max_length=32, choices=AUCTION_STATUS_CHOICES, blank=True, default="")

    # Status tracking
    qualification_status = models.CharField(max_length=32, choices=QUALIFICATION_STATUS, default="pending")
    workflow_status = models.CharField(max_length=32, choices=WORKFLOW_STATUS, default="new")

    # Parties
    plaintiff_name = models.CharField(max_length=255, blank=True, default="")
    defendant_name = models.CharField(max_length=255, blank=True, default="")

    # Property
    property_type = models.CharField(max_length=100, blank=True, default="")
    legal_description = models.TextField(blank=True, default="")
    certificate_of_title = models.TextField(blank=True, default="")

    # Assignment
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_prospects")
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_by_prospects")
    assigned_at = models.DateTimeField(null=True, blank=True)

    # Research
    lien_check_done = models.BooleanField(default=False)
    lien_check_notes = models.TextField(blank=True, default="")
    surplus_verified = models.BooleanField(default=False)
    documents_verified = models.BooleanField(default=False)

    # Contact
    skip_trace_done = models.BooleanField(default=False)
    owner_contact_info = models.TextField(blank=True, default="")
    contact_attempts = models.PositiveIntegerField(default=0)

    # Meta
    source_url = models.URLField(blank=True, default="")
    raw_data = models.JSONField(default=dict, blank=True)
    is_monitored = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("county", "case_number", "auction_date")]
        ordering = ["-auction_date", "-created_at"]

    def __str__(self):
        return f"{self.prospect_type} {self.case_number} ({self.county})"


class ProspectNote(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.prospect.case_number} by {self.author}"


class ProspectActionLog(models.Model):
    ACTION_TYPES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("qualified", "Qualified"),
        ("disqualified", "Disqualified"),
        ("assigned", "Assigned"),
        ("note_added", "Note Added"),
        ("email_sent", "Email Sent"),
        ("status_changed", "Status Changed"),
        ("converted_to_case", "Converted to Case"),
    ]

    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name="action_logs")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=64, choices=ACTION_TYPES)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} on {self.prospect.case_number}"


class ProspectEmail(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name="emails")
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="sent_prospect_emails")
    recipients = models.ManyToManyField(User, related_name="received_prospect_emails")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Email: {self.subject} re: {self.prospect.case_number}"


def log_prospect_action(prospect, user, action_type, description="", metadata=None):
    """Utility to log a prospect action."""
    return ProspectActionLog.objects.create(
        prospect=prospect,
        user=user,
        action_type=action_type,
        description=description,
        metadata=metadata or {},
    )
