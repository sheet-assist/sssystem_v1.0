from datetime import datetime
from typing import Dict, Any

from django.db.models import Q

from apps.settings_app.models import FilterCriteria


def evaluate_prospect(prospect_data: Dict[str, Any], county) -> Dict[str, Any]:
    """
    Evaluate prospect data against applicable FilterCriteria for the given county.

    Returns dict: { 'qualified': bool, 'rule': FilterCriteria|None, 'reason': str }
    Precedence: county-specific -> state-wide -> global
    """
    ptype = prospect_data.get('prospect_type')
    if not ptype:
        return {'qualified': False, 'rule': None, 'reason': 'Missing prospect_type'}

    base_qs = FilterCriteria.objects.filter(is_active=True).prefetch_related("counties")

    def _matching_rules(qs):
        for rule in qs:
            types = rule.prospect_types or ([rule.prospect_type] if rule.prospect_type else [])
            if types and ptype not in types:
                continue
            yield rule

    candidates = []
    if county:
        county_q = base_qs.filter(Q(counties=county) | Q(county=county)).distinct()
        candidates.extend(_matching_rules(county_q))
    if county and county.state:
        state_q = base_qs.filter(
            Q(state=county.state),
            Q(counties__isnull=True),
            Q(county__isnull=True),
        ).distinct()
        candidates.extend(_matching_rules(state_q))
    global_q = base_qs.filter(state__isnull=True, county__isnull=True, counties__isnull=True).distinct()
    candidates.extend(_matching_rules(global_q))

    # Evaluate candidates in order added (county -> state -> global)
    for rule in candidates:
        surplus_value = prospect_data.get('surplus_amount')
        surplus_float = None
        try:
            if surplus_value is not None:
                surplus_float = float(surplus_value)
        except Exception:
            surplus_float = None

        if rule.surplus_amount_min is not None:
            if surplus_float is None or surplus_float < float(rule.surplus_amount_min):
                return {'qualified': False, 'rule': rule, 'reason': 'surplus below minimum'}

        if rule.surplus_amount_max is not None:
            if surplus_float is not None and surplus_float > float(rule.surplus_amount_max):
                return {'qualified': False, 'rule': rule, 'reason': 'surplus above maximum'}

        # check min_date
        if rule.min_date:
            adate = prospect_data.get('auction_date')
            if isinstance(adate, str):
                try:
                    adt = datetime.fromisoformat(adate).date()
                except Exception:
                    return {'qualified': False, 'rule': rule, 'reason': 'invalid auction_date format'}
            else:
                adt = adate
            if not adt or adt < rule.min_date:
                return {'qualified': False, 'rule': rule, 'reason': f'auction_date {adt} < min_date {rule.min_date}'}

        # If other checks are configured, ensure match when present
        if rule.status_types:
            status = prospect_data.get('auction_status')
            if status and status not in rule.status_types:
                return {'qualified': False, 'rule': rule, 'reason': f'status {status} not in allowed {rule.status_types}'}

        if rule.sold_to:
            sold_to_value = prospect_data.get('sold_to') or ''
            if sold_to_value.strip() != rule.sold_to.strip():
                return {'qualified': False, 'rule': rule, 'reason': 'sold_to mismatch'}

        # passed checks for this rule -> qualified
        return {'qualified': True, 'rule': rule, 'reason': 'matches rule'}

    return {'qualified': False, 'rule': None, 'reason': 'no applicable rules'}
