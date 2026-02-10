from decimal import Decimal

from .models import FilterCriteria


def get_applicable_rules(prospect_type, county):
    """
    Get filter rules for a prospect, ordered by specificity:
    county-specific > state-wide > global.
    If county-specific rules exist, only use those.
    If not, fall back to state-wide, then global.
    """
    rules = FilterCriteria.objects.filter(
        is_active=True, prospect_type=prospect_type
    )

    county_rules = rules.filter(county=county)
    if county_rules.exists():
        return county_rules

    state_rules = rules.filter(state=county.state, county__isnull=True)
    if state_rules.exists():
        return state_rules

    return rules.filter(state__isnull=True, county__isnull=True)


def evaluate_prospect(prospect_data, county):
    """
    Evaluate a prospect dict against applicable filter criteria.

    Args:
        prospect_data: dict with keys like 'prospect_type', 'plaintiff_max_bid',
                       'assessed_value', 'final_judgment_amount', 'sale_amount',
                       'auction_date', 'auction_status', 'auction_type'
        county: County model instance

    Returns:
        (qualified: bool, reasons: list[str])
    """
    prospect_type = prospect_data.get("prospect_type", "TD")
    rules = get_applicable_rules(prospect_type, county)

    if not rules.exists():
        return True, ["No filter rules configured — auto-qualified"]

    reasons = []
    qualified = True

    for rule in rules:
        # Check plaintiff_max_bid range
        if rule.plaintiff_max_bid_min is not None or rule.plaintiff_max_bid_max is not None:
            plaintiff_bid = prospect_data.get("plaintiff_max_bid")
            if plaintiff_bid is not None:
                plaintiff_bid = Decimal(str(plaintiff_bid))
                if rule.plaintiff_max_bid_min is not None and plaintiff_bid < rule.plaintiff_max_bid_min:
                    qualified = False
                    reasons.append(
                        f"Plaintiff max bid ${plaintiff_bid} below minimum ${rule.plaintiff_max_bid_min} ({rule.name})"
                    )
                if rule.plaintiff_max_bid_max is not None and plaintiff_bid > rule.plaintiff_max_bid_max:
                    qualified = False
                    reasons.append(
                        f"Plaintiff max bid ${plaintiff_bid} above maximum ${rule.plaintiff_max_bid_max} ({rule.name})"
                    )

        # Check assessed_value range
        if rule.assessed_value_min is not None or rule.assessed_value_max is not None:
            assessed_value = prospect_data.get("assessed_value")
            if assessed_value is not None:
                assessed_value = Decimal(str(assessed_value))
                if rule.assessed_value_min is not None and assessed_value < rule.assessed_value_min:
                    qualified = False
                    reasons.append(
                        f"Assessed value ${assessed_value} below minimum ${rule.assessed_value_min} ({rule.name})"
                    )
                if rule.assessed_value_max is not None and assessed_value > rule.assessed_value_max:
                    qualified = False
                    reasons.append(
                        f"Assessed value ${assessed_value} above maximum ${rule.assessed_value_max} ({rule.name})"
                    )

        # Check final_judgment_amount range
        if rule.final_judgment_min is not None or rule.final_judgment_max is not None:
            final_judgment = prospect_data.get("final_judgment_amount")
            if final_judgment is not None:
                final_judgment = Decimal(str(final_judgment))
                if rule.final_judgment_min is not None and final_judgment < rule.final_judgment_min:
                    qualified = False
                    reasons.append(
                        f"Final judgment ${final_judgment} below minimum ${rule.final_judgment_min} ({rule.name})"
                    )
                if rule.final_judgment_max is not None and final_judgment > rule.final_judgment_max:
                    qualified = False
                    reasons.append(
                        f"Final judgment ${final_judgment} above maximum ${rule.final_judgment_max} ({rule.name})"
                    )

        # Check sale_amount range
        if rule.sale_amount_min is not None or rule.sale_amount_max is not None:
            sale_amount = prospect_data.get("sale_amount")
            if sale_amount is not None:
                sale_amount = Decimal(str(sale_amount))
                if rule.sale_amount_min is not None and sale_amount < rule.sale_amount_min:
                    qualified = False
                    reasons.append(
                        f"Sale amount ${sale_amount} below minimum ${rule.sale_amount_min} ({rule.name})"
                    )
                if rule.sale_amount_max is not None and sale_amount > rule.sale_amount_max:
                    qualified = False
                    reasons.append(
                        f"Sale amount ${sale_amount} above maximum ${rule.sale_amount_max} ({rule.name})"
                    )

        # Check minimum date
        if rule.min_date is not None:
            auction_date = prospect_data.get("auction_date")
            if auction_date and auction_date < rule.min_date:
                qualified = False
                reasons.append(
                    f"Auction date {auction_date} before minimum {rule.min_date} ({rule.name})"
                )

        # Check status types
        if rule.status_types:
            status = prospect_data.get("auction_status", "")
            if status and status not in rule.status_types:
                qualified = False
                reasons.append(
                    f"Status '{status}' not in allowed types {rule.status_types} ({rule.name})"
                )

        # Check auction types
        if rule.auction_types:
            auction_type = prospect_data.get("auction_type", "")
            if auction_type and auction_type not in rule.auction_types:
                qualified = False
                reasons.append(
                    f"Auction type '{auction_type}' not in allowed {rule.auction_types} ({rule.name})"
                )

    if qualified:
        reasons.append("Meets all filter criteria")

    return qualified, reasons
