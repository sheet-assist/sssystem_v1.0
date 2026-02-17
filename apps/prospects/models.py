from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class Prospect(models.Model):
    PROSPECT_TYPES = [
        ("TD", "Tax Deed"),
        ("TL", "Tax Lien"),
        ("SS", "Sheriff Sale"),
        ("MF", "Mortgage Foreclosure"),
    ]

    AUCTION_STATUS_CHOICES = [
        ("Canceled per Bankruptcy", "Canceled per Bankruptcy"),
        ("Canceled per County", "Canceled per County"),
        ("Canceled per Order", "Canceled per Order"),
        ("Other", "Other"),
        ("Redeemed", "Redeemed"),
        ("Sold", "Sold"),
        
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
    parcel_url = models.URLField(blank=True, default="")
    ack_url = models.URLField(blank=True, default="")
    tdm_url = models.URLField(blank=True, default="")

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
    qualification_date = models.DateTimeField(null=True, blank=True)
    disqualification_date = models.DateTimeField(null=True, blank=True)
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

    def save(self, *args, **kwargs):
        previous_status = None
        if self.pk:
            previous_status = (
                type(self).objects.filter(pk=self.pk)
                .values_list("qualification_status", flat=True)
                .first()
            )

        became_qualified = (
            self.qualification_status == "qualified"
            and (previous_status != "qualified")
        )
        became_disqualified = (
            self.qualification_status == "disqualified"
            and (previous_status != "disqualified")
        )
        if became_qualified:
            self.qualification_date = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                fields = set(update_fields)
                fields.add("qualification_date")
                kwargs["update_fields"] = list(fields)
        if became_disqualified:
            self.disqualification_date = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                fields = set(update_fields)
                fields.add("disqualification_date")
                kwargs["update_fields"] = list(fields)

        super().save(*args, **kwargs)

    @property
    def effective_ac_url(self):
        """Get AC URL, fallback to county's auction calendar URL if not set"""
        if self.ack_url:
            return self.ack_url
        if self.county and self.county.auction_calendar_url:
            return self.county.auction_calendar_url
        return None

    @property
    def effective_tdm_url(self):
        """Get TDM URL, fallback to county's RealTDM URL if not set. Only for TD and TL types."""
        # TDM fallback only applies to Tax Deed and Tax Lien
        if self.prospect_type not in ('TD', 'TL'):
            return self.tdm_url if self.tdm_url else None
        
        if self.tdm_url:
            return self.tdm_url
        if self.county and self.county.realtdm_url:
            return self.county.realtdm_url
        return None

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


class ProspectRuleNote(models.Model):
    SOURCE_CHOICES = [
        ("rule", "Rule"),
        ("scraper", "Scraper"),
        ("manual", "Manual"),
    ]
    DECISION_CHOICES = [
        ("qualified", "Qualified"),
        ("disqualified", "Disqualified"),
    ]

    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name="rule_notes")
    note = models.TextField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rule_notes",
    )
    rule = models.ForeignKey(
        "settings_app.FilterCriteria",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rule_notes",
    )
    rule_name = models.CharField(max_length=255, blank=True, default="")
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default="rule")
    decision = models.CharField(max_length=32, choices=DECISION_CHOICES, default="disqualified")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rule note for {self.prospect.case_number} ({self.created_at:%Y-%m-%d %H:%M})"


def prospect_document_upload_to(instance, filename):
    # store under MEDIA_ROOT/prospects/<prospect_pk>/<filename>
    return f"prospects/{instance.prospect.pk}/{filename}"


class ProspectDocument(models.Model):
    """Files attached to a Prospect (Digital Folder)."""
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to=prospect_document_upload_to)
    name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    size = models.PositiveIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.name or self.file.name} ({self.prospect.case_number})"

    def filename(self):
        return self.file.name.split("/")[-1]


class ProspectDocumentNote(models.Model):
    """Notes attached to a ProspectDocument."""
    document = models.ForeignKey(ProspectDocument, on_delete=models.CASCADE, related_name="notes")
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = self.created_by.get_full_name() if self.created_by else "System"
        return f"Document note by {who} on {self.created_at:%Y-%m-%d %H:%M}"

def log_prospect_action(prospect, user, action_type, description="", metadata=None):
    """Utility to log a prospect action."""
    return ProspectActionLog.objects.create(
        prospect=prospect,
        user=user,
        action_type=action_type,
        description=description,
        metadata=metadata or {},
    )


def add_rule_note(
    prospect,
    note="",
    *,
    reasons=None,
    created_by=None,
    rule=None,
    rule_name="",
    source="rule",
    decision="disqualified",
):
    """Record a rule evaluation note capturing pass/fail context."""
    content = (note or "").strip()
    resolved_rule_name = rule_name or (getattr(rule, "name", "") or "")
    reason_lines = [reason for reason in (reasons or []) if reason]
    if decision == "qualified":
        qualifier_line = f"Qualified the Rule : {resolved_rule_name or 'Unknown Rule'}"
        content = f"{content}\n\n{qualifier_line}" if content else qualifier_line
    elif decision == "disqualified" and reason_lines:
        details_block = "Failed criteria:\n" + "\n".join(f"- {reason}" for reason in reason_lines)
        content = f"{content}\n\n{details_block}" if content else details_block
    if not content:
        content = "Prospect qualified." if decision == "qualified" else "Prospect disqualified."
    return ProspectRuleNote.objects.create(
        prospect=prospect,
        note=content,
        created_by=created_by,
        rule=rule,
        rule_name=resolved_rule_name,
        source=source,
        decision=decision,
    )

