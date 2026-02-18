Plan: Finance Dashboard
Current State
Navbar "Finances" link → opens /settings/finance/ which is a settings form page (tier %, ARS %, surplus thresholds) — no charts or data visualization
Financial data exists on Prospect model: surplus_amount (used for revenue calculations)
Revenue is computed via annotation: ss_revenue_amount = surplus_amount × tier_percent / 100
ARS payout computed as: ars_amount = ss_revenue_amount × ars_tier% / 100
The main dashboard has a single "Total Revenue" KPI card — no finance charts anywhere
Goal
Replace the Finance navbar link destination with a Finance Dashboard that shows all financial data with charts and filtering. The finance settings page remains accessible from within the dashboard (via a "Settings" button).

Architecture
New Files
File	Purpose
apps/accounts/views_finance.py	FinanceDashboardView + API endpoints for chart filtering
dashboard.html	Finance dashboard template with charts
apps/accounts/urls_finance.py	URL routes for finance dashboard (namespace: finance, app_name = 'finance')
Modified Files
File	Change
urls.py	Add finance/ include with namespace
navbar.html:53	Point Finance link to new dashboard, highlight active
Dashboard Sections
1. KPI Summary Cards (top row)
Card	Data	Source
Total Surplus (Qualified)	Sum of surplus_amount where qualification_status=qualified	Prospect
SS Revenue	total_surplus × tier%	Computed
ARS Payout	ss_revenue × ars_tier%	Computed
SS Net Benefit	ss_revenue - ars_payout	Computed
Avg Surplus per Prospect	total_surplus / count	Computed
Note: Current Tier (tier_percent%) is displayed in the Finance Settings Quick Access area (section 8), not as a filterable KPI card, since it is a global setting that does not change with filters.

2. Revenue Over Time Chart (Line/Bar)
X-axis: Date (daily/monthly/yearly toggle)
Y-axis: Revenue amount
Series: Total Surplus, SS Revenue, ARS Payout
Filters: Period toggle (Daily/Monthly/Yearly) + Back/Next navigation
  - Daily: steps by 30-day windows (◀ previous 30 days, ▶ next 30 days)
  - Monthly: steps by calendar year (◀ previous year, ▶ next year), X-axis shows each month
  - Yearly: steps by 5-year windows (◀ previous 5 years, ▶ next 5 years)
  - Default on load: Daily, last 30 days from today
Data source: Prospect.qualification_date grouped by period

3. Surplus Distribution by County (Horizontal Bar)
Top 15 counties by total qualified surplus
Stacked: SS Revenue vs ARS Payout

4. Surplus Distribution by Prospect Type (Doughnut/Pie)
TD, TL, SS, MF breakdown of qualified surplus
Note: When a single prospect type is selected in the filter bar, this chart is hidden (single-segment doughnut is not useful). Shown only when multiple or all types are selected.

5. SS Revenue Distribution by Prospect Type (Bar Chart)
TD, TL, SS, MF breakdown of SS revenue
Note: Same visibility rule as section 4 — hidden when filtered to a single prospect type.

6. Revenue by Assigned User (Bar Chart)
Per-user: Surplus, SS Revenue, ARS Amount, SS Benefit
Uses user-specific ars_tier_percent from UserProfile

7. Surplus Threshold Distribution (Pie/Bar)
Count of prospects in each surplus bracket (<threshold_1, threshold_1–threshold_2, threshold_2–threshold_3, >threshold_3)

8. Finance Settings Quick Access
Button/link at top-right: "Finance Settings" → existing /settings/finance/
Displays Current Tier (tier_percent%) as a label next to the button for quick reference

Filtering Options
All charts update via AJAX from a single filter bar:

Filter	Type	Options
Date Range	Toggle + Nav	30 Days / Month / Year + ◀ ▶
State	Dropdown	All states with prospects
County	Dropdown (dependent on State)	Counties in selected state (fetched via /finance/api/counties/?state=XX)
Prospect Type	Multi-select chips	TD, TL, SS, MF
Qualification Status	Dropdown	Qualified / All
A single API endpoint /finance/api/data/ returns all chart data at once (efficient single query), filtered by the query params.

Empty States
When filters return zero results:
- KPI cards show "—" or "$0" with muted styling
- Charts display a centered "No data for selected filters" message instead of rendering empty axes
- A subtle prompt suggests broadening filter criteria

Backend Implementation Detail
FinanceDashboardView (initial page load):

Renders the template with initial data (qualified prospects, last 30 days)
Embeds initial chart data via json_script (same pattern as main dashboard)
FinanceDataAPI (AJAX endpoint):

Accepts: ?start=&end=&mode=&state=&county=&prospect_type=&qualification_status=
Returns JSON with all chart datasets:
{
  "kpi": {
    "total_surplus": 150000,
    "ss_revenue": 45000,
    "ars_payout": 9000,
    "ss_net_benefit": 36000,
    "avg_surplus": 5000,
    "prospect_count": 30
  },
  "revenue_over_time": {
    "labels": ["2026-01-01", "2026-01-02", "..."],
    "datasets": {
      "total_surplus": [1000, 2000, "..."],
      "ss_revenue": [300, 600, "..."],
      "ars_payout": [60, 120, "..."]
    }
  },
  "county_breakdown": {
    "labels": ["County A", "County B", "..."],
    "ss_revenue": [5000, 4000, "..."],
    "ars_payout": [1000, 800, "..."]
  },
  "type_distribution": {
    "labels": ["TD", "TL", "SS", "MF"],
    "surplus": [40000, 30000, 50000, 30000],
    "ss_revenue": [12000, 9000, 15000, 9000]
  },
  "user_revenue": {
    "labels": ["User A", "User B", "..."],
    "surplus": [20000, 15000, "..."],
    "ss_revenue": [6000, 4500, "..."],
    "ars_payout": [1200, 900, "..."],
    "ss_benefit": [4800, 3600, "..."]
  },
  "threshold_distribution": {
    "labels": ["< $5K", "$5K–$15K", "$15K–$30K", "> $30K"],
    "counts": [10, 12, 5, 3]
  }
}

FinanceCountiesAPI (county dropdown endpoint):

URL: /finance/api/counties/?state=XX
Returns JSON: { "counties": ["County A", "County B", "..."] }
Used by frontend to dynamically populate county dropdown when state changes

Frontend Implementation Detail
Filter Bar (horizontal, sticky below card header):

Charts (Chart.js, already loaded in base):

Line chart for revenue over time
Horizontal bar for county breakdown
Doughnut for prospect type split (hidden when single type filtered)
Bar chart for SS revenue by type (hidden when single type filtered)
Grouped bar for user revenue
Pie for surplus threshold buckets
JavaScript:

Single fetchFinanceData(params) function
Filter change → rebuild params → fetch → update all charts + KPI cards
County dropdown dynamically filtered when state changes (calls /finance/api/counties/?state=XX)
Empty state handling: check each dataset, show "No data" message if empty

URL Structure
Path	View	Name
/finance/	FinanceDashboardView	finance:dashboard
/finance/api/data/	FinanceDataAPI	finance:api-data
/finance/api/counties/	FinanceCountiesAPI	finance:api-counties

urls_finance.py:
app_name = 'finance'
urlpatterns = [
    path('', FinanceDashboardView.as_view(), name='dashboard'),
    path('api/data/', FinanceDataAPI.as_view(), name='api-data'),
    path('api/counties/', FinanceCountiesAPI.as_view(), name='api-counties'),
]

Root urls.py:
path('finance/', include('apps.accounts.urls_finance', namespace='finance')),

Navbar Change
Active state: request.resolver_match.namespace == 'finance'
Link href: {% url 'finance:dashboard' %}

No Breaking Changes
Existing /settings/finance/ route and view remain unchanged
Finance settings card on Settings home page still links to /settings/finance/
Only the navbar link changes destination