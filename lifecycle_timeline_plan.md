# Lifecycle Timeline Plan

## Goal
Add a visual timeline to both the **Prospect Detail** and **Case Detail** pages showing the full life of a record — from prospect creation → qualification/disqualification → conversion to case → case status changes (closed won / closed lost).

---

## What Gets Shown on the Timeline

Every event is pulled from existing data — **no new models or migrations needed**.

| Event | Source | Color | Icon |
|---|---|---|---|
| Prospect Created | `Prospect.created_at` | Blue | `bi-plus-circle-fill` |
| Assigned | `ProspectActionLog` (assigned) | Cyan | `bi-person-check-fill` |
| Qualified | `ProspectActionLog` (qualified) | Green | `bi-check-circle-fill` |
| Disqualified | `ProspectActionLog` (disqualified) | Red | `bi-x-circle-fill` |
| Workflow Status Change | `ProspectActionLog` (status_changed) | Gray | `bi-arrow-right-circle-fill` |
| Email Sent | `ProspectActionLog` (email_sent) | Yellow | `bi-envelope-fill` |
| Converted to Case | `ProspectActionLog` (converted_to_case) | Purple | `bi-arrow-up-circle-fill` |
| Case Created | `Case.created_at` | Green | `bi-folder2-open` |
| Contract Signed | `Case.contract_date` | Teal | `bi-file-earmark-check-fill` |
| Case Status Change | `CaseActionLog` records | Blue/Gray | `bi-arrow-right-circle-fill` |
| Case Closed Won | `CaseActionLog` (closed_won) | Green | `bi-trophy-fill` |
| Case Closed Lost | `CaseActionLog` (closed_lost) | Red | `bi-x-octagon-fill` |

Notes and rule notes are **excluded** — too frequent and low-signal for a trajectory view.

---

## Visual Design

A **vertical CSS timeline** with a colored dot and connecting line on the left, event card on the right. Events in chronological order (oldest at top). Two visual phases:
- **Prospect phase** (before conversion): left border accent = blue
- **Case phase** (after conversion): left border accent = green

Each event card shows:
- Date/time (formatted)
- Event label (bold)
- Short description
- Actor (user who triggered it, or "System")

On Case Detail: the timeline covers the full lifecycle starting from the original prospect creation.
On Prospect Detail: same, but if a case exists, case events are appended.

---

## Files to Create

### `templates/includes/_lifecycle_timeline.html`
Reusable partial. Receives `timeline` context variable (list of event dicts).
Renders the vertical timeline with Bootstrap icons and color classes.

---

## Files to Modify

### 1. `apps/prospects/views.py` — `ProspectDetailView.get_context_data()`
Add a call to `_build_lifecycle_timeline(prospect)` and pass `timeline` in context.

Helper function `_build_lifecycle_timeline(prospect)`:
- Collects events from `Prospect` fields, `ProspectActionLog`, and (if `case` exists) `Case` + `CaseActionLog`
- Returns a list of dicts sorted by `date` ascending
- Each dict: `{ date, phase, event_type, label, description, actor, icon, color }`

```python
PROSPECT_ACTION_TYPES = {
    "qualified":        ("Qualified",          "success", "bi-check-circle-fill"),
    "disqualified":     ("Disqualified",       "danger",  "bi-x-circle-fill"),
    "assigned":         ("Assigned",           "info",    "bi-person-check-fill"),
    "status_changed":   ("Workflow Changed",   "secondary","bi-arrow-right-circle-fill"),
    "converted_to_case":("Converted to Case",  "purple",  "bi-arrow-up-circle-fill"),
    "email_sent":       ("Email Sent",         "warning", "bi-envelope-fill"),
}

CASE_ACTION_COLOR = {
    "closed_won":  ("success", "bi-trophy-fill"),
    "closed_lost": ("danger",  "bi-x-octagon-fill"),
}
```

### 2. `apps/cases/views.py` — `CaseDetailView.get_context_data()`
Import and call the same `_build_lifecycle_timeline(case.prospect)` helper.
Pass `timeline` in context. Add `prospect` to `select_related` if not already there.

### 3. `templates/prospects/detail.html`
Add a new full-width section below the existing cards:
```html
<div class="card mt-4">
  <div class="card-header"><strong>Lifecycle Timeline</strong></div>
  <div class="card-body">
    {% include "includes/_lifecycle_timeline.html" %}
  </div>
</div>
```

### 4. `templates/cases/detail.html`
Add the same timeline card below the existing sections.

---

## Implementation Steps

### Step 1: Write the helper function
In `apps/prospects/views.py`, add `_build_lifecycle_timeline(prospect)` function that:
1. Starts with a "Prospect Created" event from `prospect.created_at`
2. Queries `prospect.action_logs.filter(action_type__in=PROSPECT_ACTION_TYPES).order_by("created_at")`
3. If `hasattr(prospect, 'case')`:
   - Adds "Case Created" from `case.created_at`
   - If `case.contract_date`, adds "Contract Signed" event (converted to datetime for sorting)
   - Queries `case.action_logs.order_by("created_at")` for case status events
4. Sorts all events by `date` ascending
5. Returns the sorted list

### Step 2: Update `ProspectDetailView`
- In `get_context_data()`, after the existing queryset setup, call:
  ```python
  ctx["timeline"] = _build_lifecycle_timeline(self.object)
  ```
- Ensure `prefetch_related` includes `"action_logs"`, `"action_logs__user"`, `"case__action_logs"`, `"case__action_logs__user"`

### Step 3: Update `CaseDetailView`
- In `get_context_data()`:
  ```python
  ctx["timeline"] = _build_lifecycle_timeline(self.object.prospect)
  ```
- Ensure `select_related` includes `"prospect"` and `prefetch_related` includes the action logs

### Step 4: Create `_lifecycle_timeline.html`
Vertical timeline layout using Bootstrap + Bootstrap Icons (both already loaded in base.html):

```html
{% if timeline %}
<div class="timeline">
  {% for event in timeline %}
  <div class="timeline-item {% if event.phase == 'case' %}timeline-case{% endif %}">
    <div class="timeline-dot bg-{{ event.color }}">
      <i class="bi {{ event.icon }} text-white"></i>
    </div>
    <div class="timeline-content">
      <div class="d-flex justify-content-between">
        <strong>{{ event.label }}</strong>
        <small class="text-muted">{{ event.date|date:"M d, Y H:i" }}</small>
      </div>
      {% if event.description %}<p class="mb-0 small">{{ event.description }}</p>{% endif %}
      <small class="text-muted">{{ event.actor }}</small>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<p class="text-muted">No timeline events recorded yet.</p>
{% endif %}
```

CSS (added inline in the partial or in `extra_css` block):
```css
.timeline { position: relative; padding-left: 2rem; border-left: 2px solid #dee2e6; }
.timeline-item { position: relative; margin-bottom: 1.25rem; }
.timeline-dot { position: absolute; left: -2.65rem; width: 2rem; height: 2rem;
                border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.timeline-content { background: #f8f9fa; border-radius: .375rem; padding: .5rem .75rem; }
.timeline-case .timeline-content { border-left: 3px solid #198754; }
```

### Step 5: Add `bi-purple` support
Bootstrap doesn't have `bg-purple` by default. Add to the partial's `<style>`:
```css
.bg-purple { background-color: #6f42c1 !important; }
```

---

## No Breaking Changes
- No new models, migrations, or URLs
- Existing "Recent Activity" table and "History" link on both pages are unchanged
- Timeline is purely additive — a new card section below existing content
- The helper function is private (`_build_lifecycle_timeline`) in `views.py`

---

## Verification
1. Open a prospect that has gone through full lifecycle (created → qualified → converted)
2. Open the linked case
3. Both pages should show the full timeline from prospect creation through case status
4. A prospect that was disqualified should show the disqualification event in red
5. A prospect still in pending/researching stage should show only its events so far
