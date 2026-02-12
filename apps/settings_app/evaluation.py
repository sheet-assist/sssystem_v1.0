from decimal import Decimal

from django.db.models import Q

from .models import FilterCriteria


def _matches_types(rule, prospect_type):
    types = rule.prospect_types or ([rule.prospect_type] if rule.prospect_type else [])
    if not types:
        return True
    return prospect_type in types


def _matches_date_range(rule, auction_date):
    if rule.min_date is not None and (auction_date is None or auction_date < rule.min_date):
        return False
    if rule.max_date is not None and (auction_date is None or auction_date > rule.max_date):
        return False
    return True


def _matches_filter_criteria(rule, prospect_type, auction_date):
    return _matches_types(rule, prospect_type) and _matches_date_range(rule, auction_date)


def get_applicable_rules(prospect_type, county, auction_date=None):
    """Return rules ordered by specificity (county > state > global)."""
    base = FilterCriteria.objects.filter(is_active=True).prefetch_related("counties")

    if county:
        county_qs = base.filter(Q(counties=county) | Q(county=county)).distinct()
        county_rules = [
            rule for rule in county_qs if _matches_filter_criteria(rule, prospect_type, auction_date)
        ]
        if county_rules:
            return county_rules

    if county and county.state:
        state_qs = base.filter(
            state=county.state,
            counties__isnull=True,
            county__isnull=True,
        ).distinct()
        state_rules = [
            rule for rule in state_qs if _matches_filter_criteria(rule, prospect_type, auction_date)
        ]
        if state_rules:
            return state_rules

    global_qs = base.filter(state__isnull=True, county__isnull=True, counties__isnull=True).distinct()
    global_rules = [
        rule for rule in global_qs if _matches_filter_criteria(rule, prospect_type, auction_date)
    ]
    return global_rules


def evaluate_rule_qualification(rule, prospect_data):
    """Evaluate qualification criteria only (financials, sold_to, status) for one rule."""
    reasons = []
    qualified = True

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

    if rule.surplus_amount_min is not None or rule.surplus_amount_max is not None:
        surplus = prospect_data.get("surplus_amount")
        if surplus is not None:
            surplus = Decimal(str(surplus))
            if rule.surplus_amount_min is not None and surplus < rule.surplus_amount_min:
                qualified = False
                reasons.append(
                    f"Surplus ${surplus} below minimum ${rule.surplus_amount_min} ({rule.name})"
                )
            if rule.surplus_amount_max is not None and surplus > rule.surplus_amount_max:
                qualified = False
                reasons.append(
                    f"Surplus ${surplus} above maximum ${rule.surplus_amount_max} ({rule.name})"
                )

    if rule.status_types:
        status = prospect_data.get("auction_status", "")
        if status and status not in rule.status_types:
            qualified = False
            reasons.append(
                f"Status '{status}' not in allowed types {rule.status_types} ({rule.name})"
            )

    if rule.sold_to:
        sold_to_value = (prospect_data.get("sold_to") or "").strip()
        if sold_to_value != rule.sold_to.strip():
            qualified = False
            reasons.append(
                f"Sold To '{sold_to_value}' does not match required '{rule.sold_to}' ({rule.name})"
            )

    return qualified, reasons


def evaluate_prospect(prospect_data, county):
    """
    Evaluate a prospect dict against applicable rules.

    Filter criteria determine rule applicability:
      - location (county/state/global)
      - document type
      - auction date range

    Qualification criteria determine qualified/disqualified:
      - financial thresholds
      - sold_to
      - auction status
    """
    prospect_type = prospect_data.get("prospect_type", "TD")
    auction_date = prospect_data.get("auction_date")
    rules = get_applicable_rules(prospect_type, county, auction_date=auction_date)

    if not rules:
        return True, ["No matching filter rules configured - auto-qualified"]

    reasons = []
    qualified = True
    for rule in rules:
        rule_qualified, rule_reasons = evaluate_rule_qualification(rule, prospect_data)
        if not rule_qualified:
            qualified = False
            reasons.extend(rule_reasons)

    if qualified:
        reasons.append("Meets all qualification criteria")

    return qualified, reasons
