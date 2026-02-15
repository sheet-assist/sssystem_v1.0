from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    ROLE_PROSPECTS_ONLY = "prospects_only"
    ROLE_CASES_ONLY = "cases_only"
    ROLE_BOTH = "prospects_and_cases"
    ROLE_ADMIN = "admin"

    ROLE_CHOICES = [
        (ROLE_PROSPECTS_ONLY, "Prospects Only"),
        (ROLE_CASES_ONLY, "Cases Only"),
        (ROLE_BOTH, "Prospects and Cases"),
        (ROLE_ADMIN, "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_PROSPECTS_ONLY)
    phone = models.CharField(max_length=32, blank=True, default="")
    can_manage_finance_settings = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def can_view_prospects(self):
        return self.role in {self.ROLE_PROSPECTS_ONLY, self.ROLE_BOTH, self.ROLE_ADMIN}

    @property
    def can_view_cases(self):
        return self.role in {self.ROLE_CASES_ONLY, self.ROLE_BOTH, self.ROLE_ADMIN}

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.user.is_superuser
