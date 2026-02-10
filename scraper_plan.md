# Scraper App Design Plan

## Overview
The Scraper App is a Django-based web application that manages web scraping jobs with a focus on user-friendly job management, asynchronous execution, error handling, and comprehensive logging.

---

## Execution Decisions (Confirmed)

### Infrastructure
- **Database**: Use existing `db.sqlite3` (no migration planned)
- **CSV Storage**: `scraped_data/` folder (root level, auto-create)
- **Testing Framework**: unittest (Django default)
- **Thread Pool**: `concurrent.futures.ThreadPoolExecutor`

### User & Permissions  
- **Job Creation**: Restricted to `scraper_admin` role (create new role in accounts app)
- **Job Visibility**: All logged-in users see all jobs (global)
- **Job Cancellation**: Admin-only endpoint
- **County URL Management**: Admin-only with audit trail

### Job Execution
- **Concurrent Limit**: No limit (threading handles all)
- **Thread Monitor**: Track CPU/memory in testing phase
- **Auto-Retry**: 3 attempts max with exponential backoff (5s, 25s, 125s)
- **Soft Delete**: is_active=False field (preserve audit trail)

### Data Integration
- **Locations**: LocationState/LocationCounty models already populated
- **Prospect Fields**: auction_date, status, type, all amounts, address
- **Field Mapping**: Auto-map by name similarity (auction fields ↔ prospect fields)
- **Scraper Refactoring**: Phase 2 (currently call scrape.py as-is from service)

### UI & Presentation
- **Notifications**: Toast only (no persistent panels)
- **Timestamps**: All UTC (no user timezone conversion)
- **CSV Export**: Optional alongside Prospects model storage

---

## 1. Core Features

### 1.1 Dashboard
- **Job Statistics Overview**
  - Total jobs count (all time)
  - Active jobs currently running
  - Successful jobs count (last 30 days)
  - Failed jobs count (last 30 days)
  - Pending jobs count
  

### 1.2 Recent Jobs List
- Display jobs in paginated list format
- **Filtering Options**
  - Filter by status: Failed, Success, Pending, Running
  - Filter by date range
  - Filter by state/county
- **Columns**: Job ID, Job Name, Status, Created Date, Completed Date, Status Badge, Rows Processed, Actions
- **Sorting**: By date (newest first), status, success rate

### 1.3 Job Management
#### Create New Job
- Form to create scraping jobs with fields:
  - Job name
  - State selection (dropdown)
  - County selection (dependent dropdown, populated based on state)
  - Start date (with "Today" option)
  - End date (auto-filled based on start date logic, editable)
  - Optional: Custom parameters (JSON or form fields)



#### Copy Existing Job
- "Clone Job" action on job list view, that will open create job form with prefilled paramenters from the selected row

### 1.4 Job Execution
- **Execute Job**: Run a job immediately
- **Async Processing**: Jobs run in background using async , take care of running async from sync def 
- **Real-time Status**: Show job progress and status updates
- **Retry Failed Jobs**: Button to retry a failed job with same or modified parameters

### 1.5 Date Handling Logic
- **Start Date**: User selects date or "Today"
- **End Date**: Automatically filled based on:
  - If start date is "Today", end date = Today
  - If start date is past date, end date = one week later (configurable)
  - Allow user to manually override end date
- **Date Range Validation**: End date must be ≥ Start date
### 1.5.1 URL Handling & County Management
  - County URLs stored in dedicated CountyScrapeURL model
  - Each county has a base_url field in the model
  - Format: `https://{county_slug}.realforeclose.com/`
  - Example: Miami-Dade = `https://www.miamidade.realforeclose.com/`
  - Management command to load county URLs for FL state on first setup
  - Admin interface to view and modify county URLs per-county
  - Changes take effect immediately (no app restart needed)

### 1.6 Error Handling & Logging
- **Job Error Logging**
  - Capture and store error messages
  - Log error type, traceback, timestamp
  - Store error details in database
- **Error Display**
  - Show error summary on job detail page
  - Option to view full error logs/traceback
  - Distinguish between retry-able vs fatal errors
- **Retry Mechanism**
  - Track retry count
  - Limit retries (e.g., max 3 attempts)
  - Show previous attempts and failures
-
---

## 2. Database Models

### 2.1 ScrapingJob Model
```
- id (UUID/Primary Key)
- name (CharField) - Job name
- state (ForeignKey to State/CharField)
- county (CharField or ForeignKey)
- start_date (DateField)
- end_date (DateField)
- status (CharField: pending, running, completed, failed)
- created_by (ForeignKey to User)
- created_at (DateTimeField)
- started_at (DateTimeField, nullable)
- completed_at (DateTimeField, nullable)
- rows_processed (IntegerField)
- rows_success (IntegerField)
- rows_failed (IntegerField)
- is_active (BooleanField) - For soft delete/archiving
- custom_params (JSONField, nullable)
- retry_count (IntegerField, default=0)
- max_retries (IntegerField, default=3)
- last_retry_attempt (DateTimeField, nullable)
```

### 2.2 JobExecutionLog Model
```
- id (UUID/Primary Key)
- job (ForeignKey to ScrapingJob)
- status (CharField: started, in_progress, completed, failed)
- started_at (DateTimeField)
- completed_at (DateTimeField, nullable)
- execution_duration (DurationField, nullable)
- rows_processed (IntegerField)
- task_id (CharField) - Thread ID or execution identifier
```

### 2.3 JobError Model
```
- id (UUID/Primary Key)
- job (ForeignKey to ScrapingJob)
- execution_log (ForeignKey to JobExecutionLog, nullable)
- error_type (CharField) - Exception type name (Network, Parsing, DataValidation, System)
- error_message (TextField)
- error_traceback (TextField)
- is_retryable (BooleanField)
- created_at (DateTimeField)
- retry_attempt (IntegerField)
```

### 2.4 CountyScrapeURL Model
```
- id (Primary Key)
- county (ForeignKey to LocationCounty, unique)
- base_url (URLField) - Full base URL for county scraper
- state (ForeignKey to LocationState, for quick reference)
- is_active (BooleanField, default=True)
- created_at (DateTimeField)
- updated_at (DateTimeField)
- updated_by (ForeignKey to User, nullable)
- notes (TextField, nullable) - Admin notes
```

### 2.5 UserJobDefaults Model
```
- id (Primary Key)
- user (ForeignKey to User, unique)
- last_state (ForeignKey to LocationState, nullable)
- last_county (ForeignKey to LocationCounty, nullable)
- last_start_date (DateField, nullable)
- last_end_date (DateField, nullable)
- last_custom_params (JSONField, nullable)
- updated_at (DateTimeField)
```

---

## 3. Backend Components

### 3.1 async_tasks.py
- Use Django async tasks with threading (no Celery/RQ dependency)
- `execute_scraping_job(job_id)` - Main async task using threading
- Call refactored scraper functions from job_service.py
- Error handling with error logging
- Task retry logic with exponential backoff
- Track job execution and log results to JobExecutionLog model

### 3.2 services/job_service.py
- `create_job(user, params)` - Create new job
- `execute_job(job_id)` - Trigger async execution via threading
- `get_job_stats(date_range)` - Calculate dashboard stats
- `retry_job(job_id, new_params=None)` - Retry failed job (increment retry_count)
- `clone_job(job_id, user)` - Clone existing job
- `cancel_job(job_id, user)` - Cancel running job (admin-only validation required)
- `save_user_defaults(user, params)` - Save user job defaults
- `get_user_defaults(user)` - Retrieve user defaults
- `calculate_end_date(start_date)` - Auto-calculate end date logic
- **Scraper Functions** (refactored from scrape.py):
  - `run_auctions(start_date, end_date, county_url, state, county)` - Main scraping function
  - `process_auction_date(page, auction_date, county_url, state, county)` - Daily auction processing
  - `parse_auction_item(auction_element, date, county_url, state, county)` - Parse individual auction
  - `save_to_prospects(auction_records)` - Save parsed auctions to Prospects model

### 3.3 services/job_filter_service.py
- Filter jobs by status, date range, state, county
- Search functionality
- Pagination

### 3.4 services/error_handler.py
- Log errors to JobError model
- Determine if error is retryable
- Format error messages for display
- Generate error reports

---

## 4. Frontend Components

### 4.1 Dashboard View
- **Template**: `scraper/dashboard.html`
- **Statistics Cards**: Stats overview boxes
- **Recent Jobs Table**: List of recent jobs with status
- **Quick Actions**: Create job button, Refresh stats button

### 4.2 Job List View
- **Template**: `scraper/job_list.html`
- **Filter Sidebar**
  - Status filter (checkboxes/dropdown)
  - Date range filter
  - State/County filter
- **Jobs Table**
  - Columns: ID, Name, Status, Dates, Processed, Actions
  - Action buttons: View, Execute, Retry, Clone, Delete
  - Status badges with color coding

### 4.3 Create Job Form
- **Template**: `scraper/job_create.html`
- **Form Fields**
  - Job name input
  - State dropdown (auto-loads from LocationState model)
  - County dropdown (depends on state selection)
  - Start date picker with "Today" option
  - End date picker (auto-filled)
  - Custom parameters (if applicable)
- **Form Validation**: Client-side and server-side
- **Default Values**: Pre-populate from UserJobDefaults

### 4.4 Job Detail View
- **Template**: `scraper/job_detail.html`
- **Job Information**: All job details, metadata
- **Execution History**: Table of execution logs
- **Error Details**: List of errors with full traceback option
- **Actions**: Execute, Retry, Clone, Download Results
- **Real-time Status**: WebSocket/AJAX polling for status updates

### 4.5 Job Edit Form (Clone)
- **Template**: `scraper/job_clone.html`
- Similar to create form but pre-filled with cloned job data
- Submit creates new job (doesn't modify original)

### 4.6 JavaScript Components
- **job_filter.js**: Handle filtering, pagination, sorting
- **job_form.js**: 
  - use project level county and state loading for dropdowns
  - Date auto-fill logic
  - Form validation
  - Default loading/saving logic
- **job_status.js**: Real-time status polling (5-10 sec intervals)
- **job_actions.js**: Execute, retry, clone, cancel button handlers
- **notifications.js**: Display in-app notifications on job completion/failure

---

## 5. URL Routes

```
/scraper/                                    # Dashboard
/scraper/jobs/                               # Job list
/scraper/jobs/create/                        # Create job form
/scraper/jobs/<job_id>/                      # Job detail
/scraper/jobs/<job_id>/execute/              # Execute job (POST)
/scraper/jobs/<job_id>/retry/                # Retry job (POST)
/scraper/jobs/<job_id>/clone/                # Clone job form (GET/POST)
/scraper/jobs/<job_id>/delete/               # Delete job (POST)
/scraper/api/jobs/                           # API list jobs
/scraper/api/jobs/<job_id>/status/           # API job status (for polling)
/scraper/api/defaults/                       # API get/save user defaults
/scraper/api/counties/<state>/               # API get counties by state
/scraper/api/stats/                          # API dashboard stats
```

---

## 6. Key Technical Decisions

### 6.1 Async Job Processing
- **Framework**: Django async tasks with Python threading (no Celery/RQ)
- **Advantage**: Non-blocking job execution, lightweight, no external broker needed
- **Implementation**: Use `threading.Thread` or `concurrent.futures.ThreadPoolExecutor`
- **Status Tracking**: Store thread ID in ScrapingJob.task_id (or execution log ID)
- **Polling**: AJAX polling every 5-10 seconds to check job status
- 

### 6.2 State/County Dependency
- Use AJAX/Fetch to populate counties based on state selection
- Cache state-county mapping to reduce queries

### 6.3 Date Auto-fill Logic
- **Today Option**: Store string "today" or actual date
- **Date Range Calculation**: Configurable (e.g., 7-day default window)
- **Validation**: Prevent end date before start date

### 6.4 Error Handling Strategy
- **Error Categories**:
  - **Network Errors** (retryable): Timeouts, connection failures, 5xx responses
  - **Parsing Errors** (retryable with notification): DOM structure changes, missing elements
  - **Data Validation Errors** (non-retryable): Invalid date formats, out-of-range values
  - **System Errors** (context-dependent): Out of memory, file permission issues
- **Retry Logic**:
  - Network/Parsing errors auto-retry up to max_retries (default 3)
  - Exponential backoff: 5s, 25s, 125s between attempts
  - Data Validation errors fail immediately, no retry
- **Logging**: Store error_type, error_message, full traceback in JobError model
- **User Notification**: Show error summary on job detail page, option to view full traceback

### 6.5 Default Saving
- Save defaults on every successful job creation
- Option to manually clear defaults (UI button)
- Per-user defaults in UserJobDefaults table
- Use LocationState and LocationCounty foreign keys (not strings)

### 6.6 Data Storage Strategy
- **Scraped Results**: Save to Prospects model (not just CSV)
- **CSV Output**: Optional, for legacy compatibility/export
- **Database Fields**: Map auction fields to Prospect fields where applicable
- **Audit Trail**: Track source (scraper job ID) in Prospect record

### 6.7 Real-time Updates
- AJAX polling (simpler, no WebSocket infrastructure)
- Poll every 5-10 seconds when job is running (standard frequency)
- Stop polling when job completes or fails
- Show in-app notifications on completion/failure (no email notifications)

---

## 7. User Workflows

### 7.1 Create and Execute Job
1. User clicks "Create Job" button
2. Form loads with saved defaults pre-filled
3. User selects State → County dropdown populated
4. User selects Start Date → End Date auto-filled
5. User reviews/modifies parameters
6. User clicks "Create & Execute" or "Create Only"
7. Job created and async task triggered
8. Dashboard updates with new pending job
9. Defaults saved for next time

### 7.2 Monitor Job
1. User views job list or dashboard
2. Sees job with "Running" status and progress
3. Page auto-updates job status every 5-10 seconds (AJAX polling)
4. When complete, status changes to "Success" or "Failed"
5. If failed, "Retry" button appears

### 7.3 Retry Failed Job
1. User views failed job detail
2. Sees error message and traceback
3. User can modify parameters or retry as-is
4. Click "Retry Job" button
5. New execution log created, retry_count incremented
6. Previous error remains in history
7. Job re-executes asynchronously

### 7.4 Clone and Create Variation
1. User finds successful job to clone
2. Clicks "Clone Job" → form pre-fills with job data
3. User modifies parameters (e.g., different date range, county ,state)
4. User clicks "Create"
5. New job created with modified parameters
6. Original job remains unchanged

---

## 8. Admin/Monitoring

### 8.1 Admin Interface Enhancements
- Custom admin for ScrapingJob, JobExecutionLog, JobError, CountyScrapeURL models
- Bulk actions: Retry multiple jobs, export results, cancel jobs
- Filters by status, date, user, state/county
- Read-only view of error logs with full traceback viewer
- **County URL Management**: Admin can view/edit base_url for each county
- **Job Cancellation**: Admin-only endpoint to stop running jobs
- Audit trail: Track who modified URLs and when 

### 8.2 Job Monitoring
- Thread monitor for running jobs
- Failed job notifications and in-app alerts
- Stuck job detection (running > 2 hours)
- Job execution stats and performance metrics

---

## 9. Implementation Phases

### Phase 1: Core Job Management
- [ ] Create database models (ScrapingJob, JobExecutionLog, JobError, UserJobDefaults)
- [ ] Create job service with CRUD operations
- [ ] Create job list and filter service
- [ ] Build job list view and filtering UI
- [ ] Build create job form with basic validation
- [ ] Add default saving/loading logic

### Phase 2: Async Execution & Integration

- [ ] Implement async task for job execution using threading
- [ ] Refactor scrape.py functions into job_service.py
- [ ] Create CountyScrapeURL model and admin interface
- [ ] Add task status tracking (thread monitor)
- [ ] Implement error logging and JobError model with categorization
- [ ] Create job detail view with execution history
- [ ] Add real-time status updates (AJAX polling 5-10s)
- [ ] Implement Prospects model integration for scraped data
- [ ] Add in-app notification component

### Phase 3: Advanced Features
- [ ] Implement date auto-fill logic
- [ ] Add "Today" option
- [ ] Build state/county dependent dropdowns
- [ ] Implement clone job feature
- [ ] Add retry failed job functionality
- [ ] Implement retry count limiting

### Phase 4: Dashboard & Reporting
- [ ] Build dashboard with statistics
- [ ] Create statistics calculation service
- [ ] Add job stats filters
- [ ] Build error log viewer
- [ ] Add export/report generation

### Phase 5: Testing & Quality Assurance

**Unit Tests (Model & Service Layer)**
- [ ] Test ScrapingJob model creation, validation, and state transitions
- [ ] Test JobExecutionLog model relationships and duration calculations
- [ ] Test JobError model categorization (Network/Parsing/DataValidation)
- [ ] Test CountyScrapeURL model CRUD operations
- [ ] Test UserJobDefaults model get/save operations
- [ ] Test job_service functions (create, execute, retry, clone, cancel)
- [ ] Test job_filter_service filtering by status, date, state, county
- [ ] Test error_handler categorization and retry logic
- [ ] Test stats_service calculations for dashboard
- [ ] Test form validation (job creation, clone forms)

**Integration Tests**
- [ ] Test job creation → execution → completion workflow
- [ ] Test retry logic with exponential backoff
- [ ] Test error categorization and automatic retry
- [ ] Test user defaults saving/loading in job creation
- [ ] Test county URL loading from CountyScrapeURL model
- [ ] Test job cancellation (admin-only)
- [ ] Test Prospects model data integration
- [ ] Test pagination and filtering together

**API/View Tests**
- [ ] Test job list view with filters and pagination
- [ ] Test job detail view with error logs and execution history
- [ ] Test create job view form submission
- [ ] Test clone job view
- [ ] Test dashboard statistics accuracy
- [ ] Test API endpoints: /api/jobs/, /api/jobs/<id>/status/, /api/stats/
- [ ] Test API county filtering by state
- [ ] Test API job status polling responses
- [ ] Test 404/403/500 error responses

**Async Task Tests**
- [ ] Test job execution thread spawning and tracking
- [ ] Test status updates during execution
- [ ] Test error logging during scraping
- [ ] Test thread cleanup after completion
- [ ] Test timeout handling (> 30 minutes)
- [ ] Test concurrent job execution limits

**Frontend/JavaScript Tests**
- [ ] Test job_form.js state/county dropdown dependency
- [ ] Test date auto-fill logic (today + 7 days)
- [ ] Test default values pre-population
- [ ] Test job_filter.js filtering interactions
- [ ] Test job_status.js polling (5-10s interval)
- [ ] Test notifications.js display on completion
- [ ] Test form validation error messages
- [ ] Test button action handlers (execute, retry, clone, cancel)

**Performance & Load Tests**
- [ ] Database query optimization (n+1 query check)
- [ ] Response time for job list (< 500ms with 1000 jobs)
- [ ] Status polling performance (no lag)
- [ ] Concurrent job limit testing
- [ ] Memory usage during long-running jobs

**Coverage & Documentation**
- [ ] Achieve 80%+ code coverage for services and models
- [ ] Document all test fixtures and factories
- [ ] Add API documentation with example requests/responses
- [ ] Create troubleshooting guide for common test failures
- [ ] Document performance baselines

---

## 10. File Structure to Create

```
apps/scraper/
├── models.py                 # Update with new models
├── views.py                  # Update with new views
├── forms.py                  # Create job and filter forms
├── urls.py                   # Update routes
├── admin.py                  # Update admin config
├── services/
│   ├── __init__.py
│   ├── job_service.py        # Job CRUD and business logic
│   ├── job_filter_service.py # Filtering and search
│   ├── error_handler.py      # Error logging and handling
│   └── stats_service.py      # Dashboard statistics
├── async_tasks.py            # Django async tasks with threading
├── api_views.py              # API endpoints for AJAX
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── __init__.py
│   │   └── data.py           # Test data factories and fixtures
│   ├── test_models.py        # Model tests (ScrapingJob, JobError, etc.)
│   ├── test_services.py      # Service layer tests (job_service, error_handler, etc.)
│   ├── test_views.py         # View and template rendering tests
│   ├── test_api.py           # API endpoint tests (status, stats, etc.)
│   ├── test_async_tasks.py   # Async task execution tests
│   ├── test_filters.py       # Job filtering and search tests
│   ├── test_forms.py         # Form validation tests
│   └── test_integration.py   # End-to-end workflow tests
└── static/scraper/
    └── js/
        ├── job_form.js       # Form logic and validation
        ├── job_filter.js     # Filtering functionality
        ├── job_status.js     # Real-time status updates (5-10s polling)
        ├── job_actions.js    # Action button handlers
        └── notifications.js  # In-app notifications

templates/scraper/
├── dashboard.html            # Main dashboard
├── job_list.html             # Job list with filters
├── job_create.html           # Create job form
├── job_detail.html           # Job detail and history
├── job_clone.html            # Clone job form
├── components/
│   ├── job_table.html        # Reusable job table
│   ├── job_status_badge.html # Status badge component
│   ├── filter_panel.html     # Filter sidebar
│   └── stats_cards.html      # Statistics cards
```

---

## 11. Dependencies to Add (if not present)

```
django-filter>=2.0             # Advanced filtering
python-dateutil>=2.8.0         # Date utilities
requests>=2.25.0               # HTTP requests
playwright>=1.30.0             # Browser automation (existing)
pandas>=1.0.0                  # Data processing (existing)
beautifulsoup4>=4.9.0          # HTML parsing (existing)
```
Note: No Celery, Redis, or external task brokers needed. Using Python threading instead.

---

## 12. Configuration to Add

### settings.py
```python
# Scraper Job Configuration
JOB_DEFAULT_DATE_RANGE = 7  # days (auto-fill end date)
JOB_MAX_RETRIES = 3  # Max retry attempts
JOB_RETRY_BACKOFF = True  # Exponential backoff
JOB_RETRY_DELAYS = [5, 25, 125]  # Seconds between retries
JOB_EXECUTION_TIMEOUT = 30 * 60  # 30 minutes per job execution
JOB_STATUS_POLL_INTERVAL = 5000  # 5-10 seconds in milliseconds (5000-10000)

# Scraper-specific settings
SCRAPER_HEADLESS = True  # Run Playwright headless
SCRAPER_WAIT_TIME = 30000  # 30 seconds for page load
SCRAPER_SELECTOR_WAIT = 20000  # 20 seconds for element wait

# Data storage
SCRAPER_SAVE_CSV = True  # Optional CSV export alongside DB
SCRAPER_CSV_PATH = 'scraped_data/'  # Path for CSV outputs
```

---

## 13. Testing Strategy & Tools

### 13.1 Test Fixtures & Data Factories

**Using factory_boy for consistent test data**
```python
# tests/fixtures/data.py
class ScrapingJobFactory:
    - Auto-generate state, county, dates
    - Status variants: pending, running, completed, failed
    - With/without execution logs and errors

class JobExecutionLogFactory:
    - Various durations (seconds to hours)
    - Success/failure scenarios
    - Rows processed: 0 to 10,000

class JobErrorFactory:
    - Network: timeout, connection_refused
    - Parsing: DOM_not_found, invalid_format
    - Validation: invalid_date, out_of_range
    - System: memory_error, permission_denied
```

### 13.2 Test Coverage Requirements

| Component | Minimum | Target | Notes |
|-----------|---------|--------|-------|
| Models | 85% | 95% | Focus on validation logic |
| Services | 80% | 90% | Cover all CRUD + business logic |
| Error Handler | 90% | 95% | Must cover all error types |
| Views | 75% | 85% | Forms + context data |
| Async Tasks | 75% | 85% | Thread mocking required |
| Overall | 80% | 85% | CI/CD blocks merge if < 80% |

### 13.3 Unit Tests Checklist

**Models (test_models.py)**
- [ ] ScrapingJob: creation, state transitions, validation
- [ ] JobExecutionLog: date calculations, relationships
- [ ] JobError: categorization (4 types), retryability
- [ ] CountyScrapeURL: CRUD, uniqueness constraints
- [ ] UserJobDefaults: auto-save, auto-load

**Services (test_services.py)**
- [ ] job_service.create_job() with defaults
- [ ] job_service.execute_job() triggers thread
- [ ] job_service.retry_job() increments count
- [ ] job_service.clone_job() copies parameters
- [ ] job_service.cancel_job() stops execution
- [ ] job_filter_service with combined filters
- [ ] error_handler categorizes errors correctly
- [ ] stats_service calculations match expectations

**Forms (test_forms.py)**
- [ ] JobCreationForm validates dates
- [ ] JobCreationForm prevents end_date < start_date
- [ ] JobCreationForm auto-fills defaults
- [ ] CloneJobForm pre-populates data

### 13.4 Integration Tests Checklist (test_integration.py)

- [ ] Full job creation → execution → completion workflow
- [ ] Error handling → retry → success recovery
- [ ] Job clone maintains independence
- [ ] Concurrent job execution (thread limits)
- [ ] Status polling updates correctly
- [ ] Filtering on large dataset (1000 jobs)
- [ ] Admin user can cancel jobs
- [ ] Regular user cannot cancel jobs

### 13.5 API/View Tests Checklist (test_api.py)

- [ ] GET /scraper/ returns dashboard stats
- [ ] GET /scraper/jobs/ lists with filters
- [ ] POST /scraper/jobs/create/ validates form
- [ ] GET /scraper/jobs/<id>/ shows detail + errors
- [ ] POST /scraper/jobs/<id>/execute/ returns 202
- [ ] POST /scraper/jobs/<id>/retry/ checks permissions
- [ ] GET /api/jobs/<id>/status/ returns current status
- [ ] 403 on unauthorized cancel attempt
- [ ] 404 on missing job

### 13.6 Test Execution Commands

```bash
# Run all tests
pytest apps/scraper/tests/ -v --cov=apps.scraper

# Filter by test type
pytest apps/scraper/tests/test_models.py -v
pytest apps/scraper/tests/test_integration.py -v

# Coverage report (HTML)
pytest apps/scraper/tests/ --cov=apps.scraper --cov-report=html

# Watch mode (rerun on save)
pytest-watch apps/scraper/tests/

# Specific test function
pytest apps/scraper/tests/test_models.py::TestScrapingJob::test_create_job -v
```

### 13.7 Frontend JavaScript Tests

```bash
# Jest tests
npm test -- job_form.test.js --coverage
npm test -- job_status.test.js --watch

# Coverage threshold
npm test -- --coverage --collectCoverageFrom='static/scraper/js/**'
```

### 13.8 CI/CD Pipeline

**Pre-commit Hook**
- Run unit tests only (< 30 seconds)
- Fail if any test fails

**Push to Branch**
- Run unit + integration tests (< 2 minutes)
- Generate coverage report

**Pull Request**
- Full test suite (< 5 minutes)
- Coverage report + threshold check (≥ 80%)
- Linting and type checks

**Merge to Main**
- All tests must pass
- Coverage ≥ 80%
- All security checks pass

**Pre-Deploy**
- Load test (simulate 1000 concurrent jobs)
- Performance benchmarks
- Database migration tests

---

## 14. Next Steps

1. **Validate Requirements**: Review plan with stakeholders
2. **Database Design**: Create and run migrations
3. **Start Phase 1**: Implement core models and services
4. **Iterative Development**: Complete phases in order
5. **Testing**: Write tests alongside implementation
6. **Documentation**: Update API docs and user guide

---

## Notes

- All timestamps should use UTC and convert to user's timezone in templates
- Pagination: 20-50 items per page (configurable)
- Cache job stats for 5 minutes to improve performance
- Consider rate limiting on job creation (e.g., max 10 jobs per hour per user)
- Log all job actions (create, execute, retry, delete) for audit trail
