# TDM Surplus Match Rule

## Objective
Add a new qualification rule that compares **TDM surplus amount** to the prospect's `surplus_amount` using `Prospect.case_number` (CASE #) as the lookup key.

This should behave like existing filter rules (same apply-now behavior, same disqualification reason logging).

## Rule Name
`TDM Surplus Match`

## Where It Applies
- Rule engine: `apps/settings_app/evaluation.py`
- Rule re-apply flow: `apps/settings_app/services.py`
- Rule configuration model: `apps/settings_app/models.py` (`FilterCriteria`)
- Rule configuration form/UI:
  - `apps/settings_app/forms.py`
  - `templates/settings_app/criteria_form.html`
  - `templates/settings_app/criteria_list.html`
- Prospect data model: `apps/prospects/models.py`

## Proposed Data Fields

### In `FilterCriteria`
- `check_tdm_surplus_match` (Boolean, default `False`)
  - Enables/disables this rule.
- `tdm_surplus_tolerance` (Decimal, nullable)
  - Allowed absolute difference between TDM and Prospect surplus.
  - Example: tolerance `100.00` means diff up to $100 passes.

### In `Prospect`
- `tdm_surplus_amount` (Decimal, nullable)
  - Surplus fetched from TDM by CASE #.
- `tdm_surplus_checked_at` (DateTime, nullable)
  - Last successful/attempted TDM check time.
- `tdm_lookup_status` (CharField, optional)
  - Suggested values: `ok`, `not_found`, `error`, `skipped`.

## Evaluation Logic
When `rule.check_tdm_surplus_match == True`:
1. Read prospect values:
   - `prospect_surplus = prospect_data["surplus_amount"]`
   - `tdm_surplus = prospect_data["tdm_surplus_amount"]`
2. If either value is missing, follow configured missing-data policy.
3. Compute absolute difference:
   - `diff = abs(tdm_surplus - prospect_surplus)`
4. Compare with tolerance:
   - If tolerance is set: pass when `diff <= tolerance`
   - If tolerance is null/blank: strict exact match (`diff == 0`)
5. On fail:
   - `qualified = False`
   - Append reason text including both values + diff + tolerance + rule name.

## Suggested Reason Message Format
- `TDM surplus mismatch: Prospect $12,500.00 vs TDM $11,900.00 (diff $600.00, tolerance $100.00) (RuleName)`

## Data Source and Lookup

### Lookup Key
- Use normalized `Prospect.case_number` as CASE # for TDM lookup.
- Normalization should trim spaces and optionally strip punctuation only if confirmed safe.

### Lookup Conditions
- Only run lookup when county supports TDM:
  - `county.uses_realtdm == True`
  - `county.realtdm_url` is present.

### Integration Point
- During scrape/persist and/or scheduled refresh:
  - `apps/scraper/engine/data_pipeline.py`
- Optionally add a management command for backfill:
  - `python manage.py backfill_tdm_surplus --state FL --county "Miami-Dade"`

## Behavior in Apply Now
In `apply_filter_rule` flow:
- Pass `tdm_surplus_amount` in `prospect_data` to evaluator.
- Recompute qualification based on all rules including this one.
- Save rule note with detailed mismatch reason if disqualified.

## UI/UX Requirements
- Criteria form:
  - Checkbox: `Enable TDM surplus match`
  - Numeric input: `TDM tolerance ($)`
- Criteria list:
  - Show in summary when enabled, e.g. `TDM surplus must match prospect surplus (tol $100)`

## Validation Rules
- `tdm_surplus_tolerance` must be `>= 0`.
- If `check_tdm_surplus_match` is enabled and tolerance is blank, strict match mode is used.
- If county is not TDM-enabled and rule is enabled, either:
  - hard fail validation, or
  - allow save but evaluator treats as not applicable (needs decision).

## Testing Plan

### Unit Tests (`apps/settings_app/tests.py`)
- Pass when surplus values are equal.
- Pass when difference is within tolerance.
- Fail when difference exceeds tolerance.
- Missing TDM value behavior follows selected policy.
- `Apply Now` updates qualification and logs rule note.

### Service/Integration Tests
- TDM lookup by CASE # stores `tdm_surplus_amount` on `Prospect`.
- Lookup failure states (`not_found`, `error`) are persisted and handled predictably.

## Open Decisions (Need Your Answers)
1. What should happen when TDM surplus is missing?
   - A) disqualify
   - B) skip this rule (neutral)
   - C) keep prior qualification status
2. Tolerance default:
   - A) strict `0`
   - B) fixed default (suggest `$100`)
   - C) required per rule
3. CASE # normalization:
   - A) trim only
   - B) trim + remove spaces/dashes/slashes
   - C) custom mapping per county
4. If county is not TDM-enabled but rule is enabled:
   - A) block saving rule
   - B) allow but always fail
   - C) allow but skip rule
5. Should TDM comparison apply to all prospect types or only `TD`?
6. On mismatch, should we auto-update `Prospect.surplus_amount` from TDM?
   - A) no (comparison only)
   - B) yes, always
   - C) yes, only when explicitly triggered

## Recommended Defaults
- Missing TDM surplus: **skip rule (neutral)** and log reason.
- Tolerance: **$100.00** default.
- Normalization: **trim + uppercase only** (avoid destructive normalization until county-specific patterns are confirmed).
- Non-TDM county: **allow rule but skip evaluation with note**.
- Scope: apply only to **TD** initially.
- No automatic overwrite of `Prospect.surplus_amount`.
