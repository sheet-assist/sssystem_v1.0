# Surplus Squad (SSSys™) Web Application – Detailed Requirements

## 1. Overview

The client requires a web-based application named **Surplus Squad (SS Ssys™)** to manage property surplus opportunities, prospects, and cases. The system will support multiple user roles, automated data scraping, configurable rules, and a workflow from prospect to case management.

The application is primarily designed to track and process:

* Tax Deeds (TD)
* Tax Liens
* Sheriff Sales (SS)
* Mortgage Foreclosures (MF)

The core goal is to automate identification, filtering, tracking, and conversion of prospects into active cases.

---

## 2. Branding & UI Header

* Application Name displayed as:

  * **Surplus Squad**
  * Below it: **SS Ssys™** (Trademark symbol displayed as superscript)
* Clean professional dashboard layout

---

## 3. Authentication & User Roles

### 3.1 Login System

* Secure login required

### 3.2 Role-Based Access Control

Users can have access to:

* Prospects only
* Cases only
* Both Prospects and Cases
* Admin / Settings

Permissions are assigned by user type.

---

## 4. Main Navigation Tabs

* Prospects
* Cases
* Settings (Admin/Configurable)

---

## 5. Prospect Categories

Under **Prospects**, users can select one of the following surplus types:

1. Tax Deeds (TD)
2. Tax Liens
3. Sheriff Sale (SS)
4. Mortgage Foreclosures (MF)

---

## 6. State & County Selection Flow

For all prospect types:

1. User selects State
2. User selects County (based on State)
3. System loads county-specific configuration

---

## 7. County Configuration (Settings Driven)

All county behavior is controlled via Settings to avoid repetitive setup.

For each State + County, settings include:

* Available Prospect Types (TD, Tax Lien, SS, MF)
* Uses RealTDM (Yes/No)
* Uses Auction Calendar (Yes/No)
* Auction Calendar URL
* RealTDM URL (if applicable)

These settings control front-end behavior and scraping logic.

---

## 8. Tax Deed (TD) Detailed Flow

### 8.1 RealTDM Integration

For TD counties:

* System checks if county uses RealTDM
* If Yes:

  * Display RealTDM link/icon
  * System scrapes both county data and RealTDM data
* If No:

  * Follow alternative county-specific scraping process

---

## 9. Auction Calendar Handling

If county setting = Uses Calendar = Yes:

* Display auction calendar link
* Scrape auction data from calendar
* Pull data for defined date range (e.g., last 2 years, configurable)

If No:

* Use alternate scraping method

---

## 10. Scraping Engine

### 10.1 Background Scraping

* Scraper runs automatically in background
* Initial bulk scrape (e.g., from 2024 onwards)
* Only items meeting preliminary criteria are retained

### 10.2 Incremental Monitoring

* System monitors only filtered/qualified records
* Daily checks for:

  * Date changes
  * Status updates
  * Auction updates

---

## 11. Configurable Criteria (Settings)

All filters must be configurable in Settings:

Examples:

* Minimum surplus amount (e.g., > $10,000, > $500, > $0)
* Date range (e.g., 2024 onwards)
* Status types (Live, Upcoming)
* Auction type

Admin can modify these rules without developer changes.

---

## 12. Prospect Filtering & Buckets

Each scraped record is categorized as:

* Meets Criteria (Qualified Prospect)
* Does Not Meet Criteria

"Does Not Meet Criteria" items:

* Stored separately
* Marked as checked
* Not reprocessed unless rules change

---

## 13. Prospect Assignment Workflow

Once a prospect meets criteria:

* Assigned to a user
* User performs:

  * Lien checks
  * Surplus verification
  * Document verification

---

## 14. Skip Tracing & Contact Stage

For qualified prospects:

* Skip tracing stage
* Contact property owner
* Track contact attempts

---

## 15. Conversion to Case

When contract is signed:

* Prospect is converted to Case
* Moved from Prospects to Cases
* Retains assigned user
* Case enters monitoring & follow-up workflow

---

## 16. Mortgage Foreclosure (MF) Specific

Under MF:

* Live Foreclosures
* Pre-Foreclosures

Both follow similar scraping and filtering logic.

---

## 17. Case Management

Cases module includes:

* Assigned user
* Status tracking
* Document management
* Follow-up reminders
* Ongoing monitoring

---

## 18. Reporting & Dashboards

System must provide reports for:

* Total Prospects by State/County
* Qualified vs Disqualified
* Pipeline Status
* Active Cases
* Conversion Rate (Prospect to Case)
* Touched vs Untouched Prospects

---

## 19. Manual Scrape Trigger (Optional)

Optional feature:

* Allow admin/user to manually trigger scraping for specific:

  * State
  * County
  * Date range

---

## 20. Audit & Change Tracking

* Track last scrape date per county
* Track last update date per record
* Log changes from county/auction updates

---

## 21. Future Enhancements (Not in Phase 1)

* Advanced TD criteria rules
* Deeper RealTDM workflows
* Document automation
* CRM-style communication tools

---

## 22. Non-Functional Requirements

* Secure authentication
* Role-based access
* Scalable scraping architecture
* Configurable rules engine
* Reliable background jobs
* Audit logs

---

## 23. Phase 1 Focus

Primary focus for Phase 1:

* Tax Deeds (TD)
* Calendar + RealTDM logic
* Settings-driven county configuration
* Basic scraping + filtering
* Prospect pipeline setup

---

End of Requirements Document
