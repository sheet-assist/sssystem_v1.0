# Surplus Squad (SSSys™) - Implementation Plan

## Context

Build a Django web app called **Surplus Squad (SSSys™)** to manage property surplus opportunities. The system scrapes auction data from county sites (realforeclose.com, realtaxdeed.com), filters prospects by configurable criteria, assigns qualified prospects to users for research & outreach, and converts signed contracts into tracked Cases. Starting with Florida, Phase 1 focuses on Tax Deeds (TD) with the full prospect pipeline.

**Source**: `client.md` requirements doc + `recs.jpg` whiteboard diagram + realforeclose.com field research

---

## Confirmed Decisions (from Q&A)

- **Python**: 3.12+
- **Virtual env**: Create `venv/` inside project
- **Browser automation**: **Playwright** (matching existing `scrape.py`), NOT Selenium
- **Branding**: **SSSys™** (no space, TM superscript)
- **County URLs**: Auto-generate all 67 FL counties using subdomain pattern, verify existence
- **Scraper logic**: Port from existing `scrape.py` (Playwright + BeautifulSoup, `.AUCTION_ITEM` selectors)
- **Testing**: Write Django tests for each phase before moving on
- **Database**: SQLite for now (PostgreSQL-ready schema)

---

## Branding

- Display: **Surplus Squad (SSSys<sup>TM</sup>)**
- "Surplus Squad" is the full name, "SSSys" is the short form, TM as superscript
- Clean, minimalist, professional Bootstrap 5 layout

---

## 4 Prospect Types

| Code | Name | Sub-types | Phase |
|------|------|-----------|-------|
| TD | Tax Deeds | - | Phase 1 |
| TL | Tax Liens | - | Future |
| SS | Sheriff Sales | - | Future |
| MF | Mortgage Foreclosures | Live, Pre-Foreclosure | Future |

---

## Navigation Structure (from whiteboard)

```
┌─────────────────────────────────────────────┐
│  Surplus Squad / SSSys™                     │
├──────────┬──────────┬───────────────────────┤
│ Prospects│  Cases   │  Settings (Admin)     │
└──────────┴──────────┴───────────────────────┘

Prospects Tab:                     Cases Tab:
  [TD] [TL] [SS] [MF]              Table: Type | ID | State | County | ...
    → Select State                  Type filter: TD, TL, SS, MF
      → Select County
        → View prospects list
```

---

## Project Structure

```
D:\MAP_CONFERENCE ROOM\Case Tracker\SSSystem\
├── manage.py
├── requirements.txt
├── .env
├── .gitignore
├── config/                        # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/                  # Auth, roles, profiles
│   ├── locations/                 # States, counties, county config
│   ├── prospects/                 # Prospect records, notes, assignment, filtering
│   ├── cases/                     # Converted cases, status tracking, follow-ups
│   ├── scraper/                   # Selenium engine, jobs, parsers
│   └── settings_app/             # Configurable criteria rules, system settings
├── templates/
│   ├── base.html                  # Bootstrap 5, brand header
│   ├── includes/                  # navbar, footer, messages, pagination
│   ├── dashboard.html
│   ├── accounts/
│   ├── locations/
│   ├── prospects/
│   ├── cases/
│   ├── scraper/
│   └── settings_app/
├── static/
│   ├── css/style.css
│   └── js/app.js
└── tests/                         # Shared test helpers
```

**Dependencies**: Django 5.1+, django-filter, django-environ, playwright, beautifulsoup4, lxml, pandas

---

## Database Models

### accounts app

**UserProfile** (OneToOne → Django User)
- role: choices = `prospects_only`, `cases_only`, `prospects_and_cases`, `admin`
- phone, created_at, updated_at
- Properties: `can_view_prospects`, `can_view_cases`, `is_admin`

### locations app

**State**: name, abbreviation, is_active

**County**: FK State, name, slug, fips_code, is_active, last_scraped
- Settings per county (controls scraping behavior):
  - available_prospect_types: JSONField (list of TD/TL/SS/MF)
  - uses_realtdm: BooleanField
  - uses_auction_calendar: BooleanField
  - auction_calendar_url: URLField
  - realtdm_url: URLField
  - foreclosure_url: URLField (realforeclose.com subdomain)
  - taxdeed_url: URLField (realtaxdeed.com subdomain)
  - platform: choices (realforeclose, realtaxdeed, other)

### settings_app

**FilterCriteria** (admin-configurable rules)
- name: CharField (e.g., "Florida TD Default")
- prospect_type: choices (TD/TL/SS/MF)
- state: FK State (nullable for global rules)
- county: FK County (nullable for state-wide rules)
- min_surplus_amount: DecimalField (e.g., 10000)
- min_date: DateField (e.g., 2024-01-01)
- status_types: JSONField (e.g., ["Live", "Upcoming"])
- auction_types: JSONField
- is_active: BooleanField
- created_at, updated_at

### prospects app

**Prospect** (core record - one per scraped auction item)
- **Identity**: prospect_type (TD/TL/SS/MF), auction_item_number, case_number, case_style
- **Location**: FK County, property_address, city, state, zip_code, parcel_id
- **Financial**: final_judgment_amount, opening_bid, plaintiff_max_bid, assessed_value, surplus_amount, sale_amount
- **Schedule**: auction_date, auction_time
- **Status tracking**:
  - auction_status: (scheduled/cancelled/sold_third_party/sold_plaintiff/postponed/struck_off)
  - qualification_status: (pending/qualified/disqualified)
  - workflow_status: (new/assigned/researching/skip_tracing/contacting/contract_sent/converted/dead)
- **Parties**: plaintiff_name, defendant_name
- **Property**: property_type, legal_description, certificate_of_title
- **Assignment**: assigned_to (FK User), assigned_by, assigned_at
- **Research fields**: lien_check_done (bool), lien_check_notes, surplus_verified (bool), documents_verified (bool)
- **Contact fields**: skip_trace_done (bool), owner_contact_info (text), contact_attempts (int)
- **Meta**: source_url, raw_data (JSON), is_monitored (bool), created_at, updated_at
- **Unique on**: (county, case_number, auction_date)

**ProspectNote**: FK Prospect, FK author, content, timestamps

**ProspectActionLog** (immutable audit trail)
- FK Prospect, FK user, action_type, description, metadata (JSON), created_at
- action_types: created, updated, qualified, disqualified, assigned, note_added, email_sent, status_changed, converted_to_case

**ProspectEmail** (internal team emails)
- FK Prospect, FK sender, M2M recipients, subject, body, sent_at

### cases app

**Case** (created when prospect converts)
- FK Prospect (source prospect, OneToOne)
- case_type: (TD/TL/SS/MF)
- FK County
- status: (active/monitoring/follow_up/closed_won/closed_lost)
- assigned_to: FK User
- property_address, case_number, parcel_id (copied from prospect)
- contract_date, contract_notes
- created_at, updated_at

**CaseNote**: FK Case, FK author, content, timestamps

**CaseFollowUp** (reminders)
- FK Case, FK assigned_to, due_date, description, is_completed, completed_at

**CaseActionLog**: FK Case, FK user, action_type, description, metadata, created_at

### scraper app

**ScrapeJob**: FK County, job_type (TD/TL/SS/MF), target_date, status (pending/running/completed/failed), triggered_by, record counts, error_message, timestamps

**ScrapeLog**: FK ScrapeJob, level (info/warning/error), message, raw_html, created_at

---

## Implementation Phases (test each before next)

### Phase 1: Project Scaffolding & Base Template
1. `django-admin startproject config .`
2. Create all 6 apps under `apps/`
3. `base.html` with Bootstrap 5 CDN:
   - Brand: "Surplus Squad" (line 1) + "SSSys<sup>TM</sup>" (line 2)
   - Nav tabs: **Prospects** | **Cases** | **Settings** (per whiteboard)
   - User dropdown (profile, logout)
4. Navbar, footer, messages, pagination includes
5. Configure settings.py, requirements.txt, .env, .gitignore
6. Custom `style.css` (minimal overrides)

**Test**: `manage.py check`, dev server starts, base template renders with brand

### Phase 2: Accounts - Auth & Role-Based Access
1. UserProfile model with 4 roles + post_save signal
2. Login/logout views (Django built-in)
3. Login template (centered Bootstrap card with brand)
4. Permission mixins:
   - `AdminRequiredMixin`
   - `ProspectsAccessMixin` (admin OR prospects_only OR prospects_and_cases)
   - `CasesAccessMixin` (admin OR cases_only OR prospects_and_cases)
5. Django admin: UserProfile inline on User
6. Management command: `create_admin`

**Test**: Profile auto-creation, all 4 roles enforced correctly, login/logout, redirects for unauthorized access

### Phase 3: Locations - States, Counties & County Config
1. State and County models (county includes all config fields: available types, URLs, RealTDM/calendar flags)
2. Management command: `load_states` (50 US states)
3. Management command: `load_fl_counties` (67 FL counties with realforeclose/realtaxdeed URLs, available_prospect_types)
4. Admin views: state list, county list (filtered by state), county detail/edit
5. County config form (admin edits: available types, URLs, RealTDM toggle, calendar toggle)

**Test**: 50 states load, 67 FL counties load with correct URLs, idempotent re-runs, county config saves/loads

### Phase 4: Settings App - Configurable Filter Criteria
1. FilterCriteria model
2. Admin UI: CRUD for filter rules
3. Settings page listing all active rules grouped by state/county
4. `evaluate_prospect(prospect_data, county)` function that checks against applicable rules and returns qualified/disqualified
5. Seed default rule: FL TD min_surplus > $10,000, date >= 2024-01-01

**Test**: Rule CRUD, evaluation function correctly qualifies/disqualifies sample data, rule precedence (county-specific > state-wide > global)

### Phase 5: Prospects App - Core CRUD, Filtering & List Views
1. Prospect, ProspectNote, ProspectActionLog, ProspectEmail models + migrations
2. **Prospect navigation flow** (matching whiteboard):
   - Select prospect type (TD/TL/SS/MF tabs)
   - Select state → select county
   - View prospects list for that county + type
3. ProspectListView with django-filter: county, date range, auction_status, qualification_status, workflow_status, assigned_to
4. ProspectDetailView: all fields organized in cards (identity, financial, property, parties, research, contact)
5. **Qualification buckets**:
   - "Qualified" tab: prospects meeting criteria
   - "Disqualified" tab: checked but doesn't meet criteria
   - "Pending" tab: not yet evaluated
6. Prospect action log utility: `log_prospect_action()`

**Test**: Model CRUD, unique constraints, list filtering, detail view, qualification buckets show correct records

### Phase 6: Prospects - Assignment, Notes, Research Workflow
1. AssignProspectView (admin selects user, assigns qualified prospect)
2. "My Prospects" view for assigned users (their assigned prospects only)
3. ProspectNoteCreate/Update views
4. Research workflow fields (lien check, surplus verification, document verification checkboxes)
5. Skip tracing & contact tracking (mark done, record contact info, increment attempts)
6. Workflow status transitions: new → assigned → researching → skip_tracing → contacting → contract_sent
7. Action logging on every mutation
8. Internal email system: compose email about prospect to team members, record in DB

**Test**: Assignment flow (admin assigns → user sees in "my prospects"), note CRUD, workflow status transitions, research fields save, email sends (console backend) and records, all actions logged

### Phase 7: Cases - Conversion & Case Management
1. Case, CaseNote, CaseFollowUp, CaseActionLog models
2. **Convert Prospect to Case** view:
   - Admin or assigned user triggers conversion
   - Creates Case linked to Prospect (OneToOne)
   - Sets prospect workflow_status = "converted"
   - Copies key fields (address, case_number, parcel_id, county, type)
   - Prompts for contract_date and notes
3. Cases list view (matching whiteboard: table with Type, ID, State, County columns, filterable by type TD/TL/SS/MF)
4. Case detail view with status tracking
5. Follow-up reminders: create, mark complete, list upcoming
6. Case notes and action log

**Test**: Conversion creates case correctly, prospect marked converted, case list filtering, follow-up CRUD, case notes, action logging

### Phase 8: Scraper - Parsers & Engine (Phase 1 = TD focus)
**8a: Parsers (offline, against saved HTML fixtures)**
1. Save HTML snapshots from realforeclose.com/realtaxdeed.com manually
2. `parse_calendar_page(html)` → list of dicts
3. `parse_auction_detail(html)` → dict
4. `normalize_prospect_data(raw)` → model-ready dict
5. `calculate_surplus(data)` → estimated surplus amount

**8b: Selenium engine**
1. `RealForecloseScraper` class: headless Chrome, navigate to county URL, select date, extract listings with pagination, parse all fields
2. Auto-qualification: after scraping, run `evaluate_prospect()` to bucket each record
3. Anti-blocking: random delays, user-agent rotation, rate limiting
4. Error resilience: per-record try/except, raw HTML logging

**8c: Admin UI & CLI**
1. Management command: `scrape_county --county miamidade --date 2026-03-01 --type td`
2. ScrapeTriggerView (admin form: state, county, date range, type)
3. ScrapeDashboardView (job list with status badges, record counts)
4. ScrapeLogView (detailed logs per job)
5. County `last_scraped` timestamp updated after each run

**8d: Incremental monitoring**
1. Re-scrape only monitored/qualified prospects for status changes
2. Detect date changes, status updates, auction updates
3. Log changes in ProspectActionLog

**Test**: Parsers against fixture HTML, mocked Selenium tests, save creates/updates correctly, auto-qualification works, job status transitions, admin-only access

### Phase 9: Dashboard & Reporting
1. Admin dashboard:
   - Total prospects by state/county
   - Qualified vs Disqualified counts
   - Pipeline status (prospects by workflow_status)
   - Active cases count
   - Conversion rate (prospects → cases)
   - Touched vs Untouched prospects
2. Recent activity feed (latest action logs)
3. Quick action links (trigger scrape, assign prospects)

**Test**: Dashboard renders with correct counts, stats match actual data

### Phase 10: Polish & Integration
1. Global search (case_number, parcel_id, address, defendant_name)
2. Pagination on all list views
3. Mobile responsive verification
4. Custom 404/500 pages
5. End-to-end integration test: Scrape → Auto-qualify → Admin assigns → User researches → Skip trace → Contact → Convert to Case → Case follow-up

**Test**: Full pipeline flow, responsive layout, search accuracy

---

## URL Structure

```
/                                → Redirect to /dashboard/
/dashboard/                      → Admin dashboard (reporting)
/accounts/login/                 → Login
/accounts/logout/                → Logout
/accounts/profile/               → User profile
/accounts/users/                 → User list (admin)

/prospects/                      → Type selection (TD/TL/SS/MF cards)
/prospects/<type>/               → State selection for type
/prospects/<type>/<state>/       → County selection
/prospects/<type>/<state>/<county>/  → Prospect list (filterable)
/prospects/<id>/                 → Prospect detail
/prospects/<id>/assign/          → Assign to user (admin)
/prospects/<id>/notes/add/       → Add note
/prospects/<id>/email/           → Send team email
/prospects/<id>/convert/         → Convert to case
/prospects/<id>/history/         → Action history
/prospects/my/                   → My assigned prospects

/cases/                          → Case list (filterable by type, state, county)
/cases/<id>/                     → Case detail
/cases/<id>/notes/add/           → Add case note
/cases/<id>/followups/add/       → Add follow-up
/cases/<id>/history/             → Case action history

/scraper/dashboard/              → Scrape jobs list (admin)
/scraper/trigger/                → Start new scrape (admin)
/scraper/jobs/<id>/              → Job detail + logs

/settings/                       → Settings home (admin)
/settings/criteria/              → Filter criteria list
/settings/criteria/add/          → Add new rule
/settings/criteria/<id>/edit/    → Edit rule
/settings/counties/<id>/config/  → County configuration
```

---

## Role Access Matrix

| View | Admin | Prospects Only | Cases Only | Both |
|------|-------|---------------|------------|------|
| Dashboard | Full stats | Prospect stats | Case stats | Full stats |
| Prospects tab | All + assign | Assigned only | Hidden | All (view) |
| Cases tab | All | Hidden | All | All |
| Settings tab | Full access | Hidden | Hidden | Hidden |
| Scraper | Full access | Hidden | Hidden | Hidden |
| Assign prospect | Yes | No | No | No |
| Convert to case | Yes | Yes (own) | No | Yes (own) |

---

## Key Design Decisions

- **Brand**: "Surplus Squad" line 1, "SSSys<sup>TM</sup>" line 2 in navbar
- **4 roles** (not just admin/user): prospects_only, cases_only, prospects_and_cases, admin
- **Prospect → Case pipeline**: Scrape → Qualify → Assign → Research → Skip Trace → Contact → Convert
- **Settings-driven**: Filter criteria and county config are admin-editable, no code changes needed
- **Qualification engine**: `evaluate_prospect()` runs criteria rules automatically after scraping
- **Disqualified bucket**: Stored but not reprocessed unless rules change
- **Incremental monitoring**: Only re-check qualified/monitored records for status changes
- **SQLite** for now, schema supports PostgreSQL migration later
- **Console email backend** for dev, SMTP via .env for production

---

## Verification

After each phase:
```bash
python manage.py test                    # All tests pass
python manage.py check                   # System check passes
python manage.py runserver               # Manual smoke test
```

Final integration test: Scrape FL TD auctions → Auto-qualify by surplus > $10k → Admin assigns to user → User does lien check + skip trace → User contacts owner → Contract signed → Convert to Case → Case follow-up created → Dashboard shows updated stats
