from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone

from apps.prospects.models import Prospect, add_rule_note, log_prospect_action

from .evaluation import evaluate_rule_qualification
from .models import FilterCriteria


def _prospects_for_rule(rule: FilterCriteria):
    counties = list(rule.counties.all())
    queryset = Prospect.objects.all()

    if counties:
        queryset = queryset.filter(county__in=counties)
    elif rule.county:
        queryset = queryset.filter(county=rule.county)
    elif rule.state:
        queryset = queryset.filter(county__state=rule.state)

    types = rule.prospect_types or ([rule.prospect_type] if rule.prospect_type else [])
    if types:
        queryset = queryset.filter(prospect_type__in=types)

    if rule.min_date:
        queryset = queryset.filter(auction_date__gte=rule.min_date)
    if rule.max_date:
        queryset = queryset.filter(auction_date__lte=rule.max_date)

    return queryset.select_related("county")


def apply_filter_rule(rule: FilterCriteria, acting_user: Optional[object] = None) -> Dict[str, int]:
    """Re-evaluate all prospects impacted by the given rule."""
    queryset = _prospects_for_rule(rule)
    summary = {"processed": 0, "updated": 0, "qualified": 0, "disqualified": 0}
    actor_label = (
        acting_user.get_username()
        if acting_user is not None and hasattr(acting_user, "get_username")
        else "System"
    )
    applied_at = timezone.localtime(timezone.now())

    with transaction.atomic():
        for prospect in queryset.iterator(chunk_size=200):
            summary["processed"] += 1
            prospect_data = {
                "prospect_type": prospect.prospect_type,
                "plaintiff_max_bid": prospect.plaintiff_max_bid,
                "assessed_value": prospect.assessed_value,
                "final_judgment_amount": prospect.final_judgment_amount,
                "sale_amount": prospect.sale_amount,
                "surplus_amount": prospect.surplus_amount,
                "auction_date": prospect.auction_date,
                "auction_status": prospect.auction_status,
                "sold_to": prospect.sold_to,
            }
            qualified, reasons = evaluate_rule_qualification(rule, prospect_data)
            new_status = "qualified" if qualified else "disqualified"
            note_text = (
                f"Rule '{rule.name}' applied by {actor_label} at "
                f"{applied_at:%Y-%m-%d %H:%M:%S %Z} marked this prospect as {new_status}."
            )

            if prospect.qualification_status == new_status:
                add_rule_note(
                    prospect,
                    note=note_text,
                    reasons=reasons if not qualified else None,
                    created_by=acting_user,
                    rule=rule,
                    rule_name=rule.name,
                    source="rule",
                    decision=new_status,
                )
                continue

            prospect.qualification_status = new_status
            prospect.save(update_fields=["qualification_status", "updated_at"])
            summary["updated"] += 1
            summary[new_status] += 1

            description = f"Rule '{rule.name}' re-applied via Apply Now."
            if reasons:
                description += f" Reasons: {'; '.join(reasons[:3])}"
            log_prospect_action(
                prospect,
                acting_user,
                new_status,
                description=description,
                metadata={
                    "rule_id": rule.pk,
                    "applied_via": "apply_now",
                },
            )

            add_rule_note(
                prospect,
                note=note_text,
                reasons=reasons if not qualified else None,
                created_by=acting_user,
                rule=rule,
                rule_name=rule.name,
                source="rule",
                decision=new_status,
            )

    return summary


def apply_rule_to_queryset(rule: FilterCriteria, queryset, acting_user: Optional[object] = None) -> Dict[str, int]:
    """Apply the given FilterCriteria rule to the provided Prospect queryset.

    Returns the same summary dict structure as `apply_filter_rule`.
    """
    summary = {"processed": 0, "updated": 0, "qualified": 0, "disqualified": 0}
    actor_label = (
        acting_user.get_username()
        if acting_user is not None and hasattr(acting_user, "get_username")
        else "System"
    )
    applied_at = timezone.localtime(timezone.now())

    with transaction.atomic():
        for prospect in queryset.iterator(chunk_size=200):
            summary["processed"] += 1
            prospect_data = {
                "prospect_type": prospect.prospect_type,
                "plaintiff_max_bid": prospect.plaintiff_max_bid,
                "assessed_value": prospect.assessed_value,
                "final_judgment_amount": prospect.final_judgment_amount,
                "sale_amount": prospect.sale_amount,
                "surplus_amount": prospect.surplus_amount,
                "auction_date": prospect.auction_date,
                "auction_status": prospect.auction_status,
                "sold_to": prospect.sold_to,
            }
            qualified, reasons = evaluate_rule_qualification(rule, prospect_data)
            new_status = "qualified" if qualified else "disqualified"
            note_text = (
                f"Rule '{rule.name}' applied by {actor_label} at "
                f"{applied_at:%Y-%m-%d %H:%M:%S %Z} marked this prospect as {new_status}."
            )

            if prospect.qualification_status == new_status:
                add_rule_note(
                    prospect,
                    note=note_text,
                    reasons=reasons if not qualified else None,
                    created_by=acting_user,
                    rule=rule,
                    rule_name=rule.name,
                    source="rule",
                    decision=new_status,
                )
                continue

            prospect.qualification_status = new_status
            prospect.save(update_fields=["qualification_status", "updated_at"])
            summary["updated"] += 1
            summary[new_status] += 1

            description = f"Rule '{rule.name}' applied to upload prospects."
            if reasons:
                description += f" Reasons: {'; '.join(reasons[:3])}"
            log_prospect_action(
                prospect,
                acting_user,
                new_status,
                description=description,
                metadata={
                    "rule_id": rule.pk,
                    "applied_via": "upload_apply",
                },
            )

            add_rule_note(
                prospect,
                note=note_text,
                reasons=reasons if not qualified else None,
                created_by=acting_user,
                rule=rule,
                rule_name=rule.name,
                source="rule",
                decision=new_status,
            )

    return summary
