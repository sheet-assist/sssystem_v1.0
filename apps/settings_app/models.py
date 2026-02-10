from django.db import models


class FilterCriteria(models.Model):
    PROSPECT_TYPES = [
        ("TD", "Tax Deed"),
        ("TL", "Tax Lien"),
        ("SS", "Sheriff Sale"),
        ("MF", "Mortgage Foreclosure"),
    ]

    name = models.CharField(max_length=200)
    prospect_type = models.CharField(max_length=8, choices=PROSPECT_TYPES)
    state = models.ForeignKey(
        "locations.State", on_delete=models.CASCADE, null=True, blank=True
    )
    county = models.ForeignKey(
        "locations.County", on_delete=models.CASCADE, null=True, blank=True
    )
    
    # Financial Criteria (replaces min_surplus_amount)
    plaintiff_max_bid_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum plaintiff maximum bid amount"
    )
    plaintiff_max_bid_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum plaintiff maximum bid amount"
    )
    assessed_value_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum assessed property value"
    )
    assessed_value_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum assessed property value"
    )
    final_judgment_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum final judgment amount"
    )
    final_judgment_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum final judgment amount"
    )
    sale_amount_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum sale amount"
    )
    sale_amount_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum sale amount"
    )
    
    min_date = models.DateField(null=True, blank=True)
    status_types = models.JSONField(default=list, blank=True)
    auction_types = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "filter criteria"
        ordering = ["-is_active", "state__name", "county__name", "name"]

    def __str__(self):
        scope = "Global"
        if self.county:
            scope = f"County: {self.county.name}"
        elif self.state:
            scope = f"State: {self.state.name}"
        return f"{self.name} ({self.prospect_type}) - {scope}"
