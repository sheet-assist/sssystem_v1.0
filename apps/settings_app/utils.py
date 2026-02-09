from datetime import datetime
from typing import Dict, Any, Optional

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

    candidates = []
    # county-specific
    if county:
        candidates.extend(list(FilterCriteria.objects.filter(is_active=True, prospect_type=ptype, county=county)))
    # state-wide
    if county and county.state:
        candidates.extend(list(FilterCriteria.objects.filter(is_active=True, prospect_type=ptype, state=county.state, county__isnull=True)))
    # global
    candidates.extend(list(FilterCriteria.objects.filter(is_active=True, prospect_type=ptype, state__isnull=True, county__isnull=True)))

    # Evaluate candidates in order added (county -> state -> global)
    for rule in candidates:
        # check min_surplus_amount
        if rule.min_surplus_amount is not None:
            try:
                surplus = float(prospect_data.get('surplus_amount') or 0)
            except Exception:
                surplus = 0
            if surplus < float(rule.min_surplus_amount):
                return {'qualified': False, 'rule': rule, 'reason': f'surplus {surplus} < min {rule.min_surplus_amount}'}

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

        # If other checks (status_types, auction_types) are configured, ensure match when present
        if rule.status_types:
            status = prospect_data.get('auction_status')
            if status and status not in rule.status_types:
                return {'qualified': False, 'rule': rule, 'reason': f'status {status} not in allowed {rule.status_types}'}

        # passed checks for this rule -> qualified
        return {'qualified': True, 'rule': rule, 'reason': 'matches rule'}

    return {'qualified': False, 'rule': None, 'reason': 'no applicable rules'}
