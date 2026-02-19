from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class FilterCriteria(models.Model):
    PROSPECT_TYPES = [
        ("TD", "Tax Deed"),
        ("TL", "Tax Lien"),
        ("SS", "Sheriff Sale"),
        ("MF", "Mortgage Foreclosure"),
    ]

    name = models.CharField(max_length=200)
    prospect_type = models.CharField(max_length=8, choices=PROSPECT_TYPES, blank=True)
    prospect_types = models.JSONField(default=list, blank=True)
    state = models.ForeignKey(
        "locations.State", on_delete=models.CASCADE, null=True, blank=True
    )
    county = models.ForeignKey(
        "locations.County", on_delete=models.CASCADE, null=True, blank=True
    )
    counties = models.ManyToManyField(
        "locations.County", blank=True, related_name="filter_criteria_rules"
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
    surplus_amount_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Minimum surplus amount"
    )
    surplus_amount_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Maximum surplus amount"
    )
    sold_to = models.CharField(max_length=255, blank=True, default="",
                               help_text="Match exact 'Sold To' value")
    
    min_date = models.DateField(null=True, blank=True)
    max_date = models.DateField(
        null=True,
        blank=True,
        help_text="Maximum auction date allowed",
    )
    status_types = models.JSONField(default=list, blank=True)
    auction_types = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "filter criteria"
        ordering = ["-is_active", "state__name", "name"]

    def __str__(self):
        scope = "Global"
        county_list = list(self.counties.values_list("name", flat=True)) if self.pk else []
        if county_list:
            names = ", ".join(county_list[:2])
            extra = len(county_list) - 2
            if extra > 0:
                names = f"{names} (+{extra})"
            scope = f"Counties: {names}"
        elif self.county:
            scope = f"County: {self.county.name}"
        elif self.state:
            scope = f"State: {self.state.name}"

        type_labels = dict(self.PROSPECT_TYPES)
        types = self.prospect_types or ([self.prospect_type] if self.prospect_type else [])
        display_types = [type_labels.get(code, code) for code in types]
        type_str = ", ".join(display_types) if display_types else "All Types"
        return f"{self.name} ({type_str}) - {scope}"

    def get_verbose_summary(self):
        conditions = []

        def money_text(label, min_value, max_value):
            if min_value is None and max_value is None:
                return None
            if min_value is not None and max_value is None:
                return f"{label} higher than or equal to ${min_value:,.0f} USD"
            if min_value is None and max_value is not None:
                return f"{label} up to ${max_value:,.0f} USD"
            return f"{label} between ${min_value:,.0f} USD and ${max_value:,.0f} USD"

        for text in [
            money_text("plaintiff max bid", self.plaintiff_max_bid_min, self.plaintiff_max_bid_max),
            money_text("assessed value", self.assessed_value_min, self.assessed_value_max),
            money_text("final judgment", self.final_judgment_min, self.final_judgment_max),
            money_text("sale amount", self.sale_amount_min, self.sale_amount_max),
            money_text("surplus amount", self.surplus_amount_min, self.surplus_amount_max),
        ]:
            if text:
                conditions.append(text)

        if self.sold_to:
            conditions.append(f"sold to {self.sold_to}")

        if self.min_date or self.max_date:
            if self.min_date and self.max_date:
                conditions.append(f"auction date between {self.min_date} and {self.max_date}")
            elif self.min_date:
                conditions.append(f"auction date on or after {self.min_date}")
            elif self.max_date:
                conditions.append(f"auction date on or before {self.max_date}")

        if self.status_types:
            conditions.append(f"status in {', '.join(self.status_types)}")

        location_text = ""
        if self.counties.exists():
            county_qs = self.counties.all()
            county_count = county_qs.count()
            if self.state:
                state_code = self.state.abbreviation or self.state.name
                state_counties_count = self.state.counties.count()
                if state_counties_count > 0 and county_count == state_counties_count:
                    location_text = f"in all counties of {state_code} state"
                else:
                    county_names = list(county_qs.values_list("name", flat=True))
                    location_text = f"in counties: {', '.join(county_names)}"
            else:
                county_names = list(county_qs.values_list("name", flat=True))
                location_text = f"in counties: {', '.join(county_names)}"
        elif self.state:
            state_code = self.state.abbreviation or self.state.name
            location_text = f"in {state_code} state"
        else:
            location_text = "in all states"

        if conditions:
            condition_text = " and ".join(conditions)
            sentence = f"{condition_text} {location_text} will be marked as qualified."
            return sentence[:1].upper() + sentence[1:]
        return f"Prospects {location_text} will be marked as qualified."


class SSRevenueSetting(models.Model):
    TIER_CHOICES = [
        (10, "10%"),
        (13, "13%"),
        (15, "15%"),
        (18, "18%"),
        (25, "25%"),
        (30, "30%"),
    ]

    tier_percent = models.PositiveSmallIntegerField(choices=TIER_CHOICES, default=15)
    ARS_TIER_CHOICES = [
        (1, "1%"),
        (3, "3%"),
        (5, "5%"),
        (7, "7%"),
        (8, "8%"),
        (9, "9%"),
        (10, "10%"),
    ]
    ars_tier_percent = models.PositiveSmallIntegerField(choices=ARS_TIER_CHOICES, default=5)
    
    # Surplus Amount Filter Thresholds (in dollars)
    surplus_threshold_1 = models.DecimalField(
        max_digits=12, decimal_places=2, default=50000,
        help_text="First surplus threshold (e.g., Less than $50,000)"
    )
    surplus_threshold_2 = models.DecimalField(
        max_digits=12, decimal_places=2, default=100000,
        help_text="Second surplus threshold (e.g., Less than $100,000)"
    )
    surplus_threshold_3 = models.DecimalField(
        max_digits=12, decimal_places=2, default=150000,
        help_text="Third surplus threshold (e.g., Less than $150,000)"
    )
    
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_ss_revenue_settings"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SS Revenue Setting"
        verbose_name_plural = "SS Revenue Settings"

    def __str__(self):
        return f"SS Revenue Tier: {self.tier_percent}% | ARS Tier: {self.ars_tier_percent}%"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"tier_percent": 15, "ars_tier_percent": 5},
        )
        return obj
