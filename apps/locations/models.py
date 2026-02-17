from django.db import models
from django.utils import timezone


class State(models.Model):
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=5, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class County(models.Model):
    PLATFORM_CHOICES = [
        ("realforeclose", "RealForeclose"),
        ("realtaxdeed", "RealTaxDeed"),
        ("other", "Other"),
    ]

    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="counties")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150)
    fips_code = models.CharField(max_length=10, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_scraped = models.DateTimeField(blank=True, null=True)

    # County configuration
    auction_calendar_url = models.URLField(blank=True, default="")
    realtdm_url = models.URLField(blank=True, default="")
    platform = models.CharField(max_length=32, choices=PLATFORM_CHOICES, default="other")

    class Meta:
        verbose_name_plural = "counties"
        unique_together = [("state", "slug")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.state.abbreviation}"

    def update_last_scraped(self):
        self.last_scraped = timezone.now()
        self.save(update_fields=["last_scraped"])
