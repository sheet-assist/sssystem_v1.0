from django.db import models
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class Case(models.Model):
    CASE_STATUS = [
        ('active', 'Active'),
        ('monitoring', 'Monitoring'),
        ('follow_up', 'Follow Up'),
        ('closed_won', 'Closed Won'),
        ('closed_lost', 'Closed Lost'),
    ]

    prospect = models.OneToOneField('prospects.Prospect', on_delete=models.CASCADE, related_name='case')
    case_type = models.CharField(max_length=8, blank=True)
    county = models.ForeignKey('locations.County', on_delete=models.CASCADE)
    status = models.CharField(max_length=32, choices=CASE_STATUS, default='active')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    property_address = models.CharField(max_length=400, blank=True)
    case_number = models.CharField(max_length=200, blank=True)
    parcel_id = models.CharField(max_length=200, blank=True)

    contract_date = models.DateField(null=True, blank=True)
    contract_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Case {self.case_number or self.pk} ({self.case_type})"

    def get_absolute_url(self):
        return reverse('cases:detail', args=[self.pk])


class CaseNote(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Note by {self.author} on {self.case}"


class CaseFollowUp(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='followups')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField()
    description = models.TextField()
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"FollowUp {self.case} due {self.due_date}"


class CaseActionLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='action_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.action_type} on {self.case}"
