# Phase 1: Core Job Management - Implementation Guide

**Status**: Ready to Execute  
**Start Date**: February 10, 2026  
**Estimated Duration**: 3-5 days  

---

## Overview

Phase 1 focuses on creating the database models, forms, and basic views for job management. This is the foundation for all subsequent phases.

---

## Implementation Checklist

### Step 1: Create Models (models.py)

**Create 5 new models:**

```python
# apps/scraper/models.py

class ScrapingJob(models.Model):
    # UUIDs for IDs, ForeignKey to User, CharField for state/county
    # Status choices: pending, running, completed, failed
    # Datetime fields for timestamps
    # IntegerFields for rows_processed, rows_success, rows_failed
    # JSONField for custom_params
    # BooleanField is_active for soft delete
    # Meta: ordering by created_at DESC

class JobExecutionLog(models.Model):
    # ForeignKey to ScrapingJob
    # Status choices: started, in_progress, completed, failed
    # DateTimeFields for started_at, completed_at
    # DurationField for execution_duration
    # IntegerField rows_processed
    # CharField task_id (Thread ID or execution identifier)

class JobError(models.Model):
    # ForeignKey to ScrapingJob
    # ForeignKey to JobExecutionLog (nullable)
    # CharField error_type choices: Network, Parsing, DataValidation, System
    # TextField error_message, error_traceback
    # BooleanField is_retryable
    # DateTimeField created_at
    # IntegerField retry_attempt

class CountyScrapeURL(models.Model):
    # ForeignKey to LocationCounty (unique)
    # ForeignKey to LocationState (for quick ref)
    # URLField base_url
    # BooleanField is_active (default=True)
    # DateTimeFields created_at, updated_at
    # ForeignKey to User updated_by (nullable)
    # TextField notes (nullable)
    # Meta: unique_together = [['county']]

class UserJobDefaults(models.Model):
    # ForeignKey to User (unique)
    # ForeignKey to LocationState (nullable)
    # ForeignKey to LocationCounty (nullable)
    # DateField last_start_date (nullable)
    # DateField last_end_date (nullable)
    # JSONField last_custom_params (nullable)
    # DateTimeField updated_at
    # Meta: get_latest_by = 'updated_at'
```

**Action**: Create apps/scraper/models.py with complete model definitions

---

### Step 2: Create Forms (forms.py)

**Create 2 forms:**

```python
# apps/scraper/forms.py

class JobCreationForm(Form):
    # CharField: job_name
    # ModelChoiceField: state (from LocationState)
    # ModelChoiceField: county (from LocationCounty, optional initially)
    # DateField: start_date (with "Today" widget)
    # DateField: end_date (auto-filled clientside)
    # Validation: end_date >= start_date

class JobFilterForm(Form):
    # ChoiceField: status (pending, running, success, failed)
    # DateRangeField: date_range
    # ModelChoiceField: state
    # ModelChoiceField: county
```

**Action**: Create apps/scraper/forms.py

---

### Step 3: Create Management Command

**Create**: `python manage.py load_county_urls`

```python
# apps/scraper/management/commands/load_county_urls.py

class Command(BaseCommand):
    # Load Florida county URLs
    # Data: Miami-Dade, Broward, Palm Beach, etc.
    # Create CountyScrapeURL records with base_urls
    # Skip if already exists (check is_active)
```

**Base URL Format**: `https://{county_slug}.realforeclose.com/`

**Example Data**:
- Miami-Dade: `https://www.miamidade.realforeclose.com/`
- Broward: `https://www.broward.realforeclose.com/`
- etc.

---

### Step 4: Add scraper_admin Role

**Update accounts/models.py or create permission group:**

```python
# In accounts signals or admin

# Create permission group 'scraper_admin'
# Assign permissions:
#  - scraper.add_scrapingjob
#  - scraper.change_scrapingjob
#  - scraper.delete_scrapingjob
#  - scraper.view_scrapingjob
#  - scraper.change_countyscrapeurl
#  - scraper.add_countyscrapeurl
```

**Action**: Add scraper_admin permission group or role

---

### Step 5: Create Migrations

```bash
# Generate migrations
python manage.py makemigrations scraper

# Review migration files
cat apps/scraper/migrations/0001_initial.py

# Apply migrations
python manage.py migrate scraper
```

---

### Step 6: Create CSV Export Folder

```bash
# Create scraped_data folder
mkdir scraped_data

# Add to .gitignore
echo "scraped_data/" >> .gitignore
```

---

### Step 7: Create Admin Interface

```python
# apps/scraper/admin.py

@admin.register(ScrapingJob)
class ScrapingJobAdmin(admin.ModelAdmin):
    # List display: name, status, created_by, created_at, completed_at
    # List filter: status, created_at, created_by
    # Search fields: name, created_by__username
    # Readonly fields: created_at, updated_at, task_id

@admin.register(CountyScrapeURL)
class CountyScrapeURLAdmin(admin.ModelAdmin):
    # List display: county, state, base_url, is_active, updated_at
    # List filter: state, is_active
    # Search fields: county__name, state__name
    # Fields: county, state, base_url, is_active, updated_by, notes
```

---

### Step 8: Create Basic Views

```python
# apps/scraper/views.py

class DashboardView(TemplateView):
    # Render dashboard.html
    # Context: recent_jobs, job_stats, pending_jobs

class JobListView(ListView):
    # Paginate: 20 items per page
    # Filter: by status, date range, state, county
    # Template: job_list.html

class JobCreateView(CreateView):
    # Form: JobCreationForm
    # Save: create_by = request.user
    # Redirect: job detail page

class JobDetailView(DetailView):
    # Show: job info, execution logs, errors
    # Actions: Execute, Retry, Clone, Delete buttons
    # Template: job_detail.html
```

---

### Step 9: Create URLs

```python
# apps/scraper/urls.py

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('jobs/', JobListView.as_view(), name='job_list'),
    path('jobs/create/', JobCreateView.as_view(), name='job_create'),
    path('jobs/<uuid:pk>/', JobDetailView.as_view(), name='job_detail'),
    # Add to config/urls.py:
    # path('scraper/', include('apps.scraper.urls')),
]
```

---

### Step 10: Test Phase 1

```bash
# Run Django shell
python manage.py shell

# Test model creation
from apps.scraper.models import *
from apps.locations.models import LocationCounty, LocationState

# Create test data
fl = LocationState.objects.get(code='FL')
county = LocationCounty.objects.get(name='Miami-Dade', state=fl)
url = CountyScrapeURL.objects.create(
    county=county,
    state=fl,
    base_url='https://www.miamidade.realforeclose.com/'
)
print(url)

# Test job creation
from django.contrib.auth.models import User
user = User.objects.first()
job = ScrapingJob.objects.create(
    name='Test Job',
    state=fl.code,
    county=county.name,
    start_date='2026-02-10',
    end_date='2026-02-17',
    created_by=user
)
print(job)
```

---

### Step 11: Load Initial Data

```bash
# Create superuser if not exists
python manage.py createsuperuser

# Load county URLs
python manage.py load_county_urls

# Verify data
python manage.py shell
from apps.scraper.models import CountyScrapeURL
print(CountyScrapeURL.objects.count())  # Should show FL counties
```

---

### Step 12: Verify Everything

```bash
# Run migrations
python manage.py migrate

# Check for errors
python manage.py check

# Run development server
python manage.py runserver

# Visit:
# http://localhost:8000/admin/  (login with superuser)
# http://localhost:8000/scraper/  (should show dashboard)
```

---

## Execution Order

1. **Create models.py** (30 min)
2. **Create forms.py** (20 min)
3. **Create management command** (15 min)
4. **Add scraper_admin role** (10 min)
5. **Run makemigrations & migrate** (5 min)
6. **Create CSV folder** (2 min)
7. **Create admin.py** (20 min)
8. **Create views.py** (30 min)
9. **Create urls.py** (10 min)
10. **Test in Django shell** (20 min)
11. **Load initial data** (10 min)
12. **Verify with runserver** (10 min)

**Total: ~3 hours of core development + testing**

---

## Success Criteria (Phase 1 Complete)

✅ All 5 models created and migrated  
✅ ScrapingJob records can be created  
✅ Dashboard view loads  
✅ Job list view shows paginated jobs  
✅ County URLs loaded via management command  
✅ Admin interface functional  
✅ No migration errors  
✅ scraper_admin role can create jobs  
✅ CSV folder created  
✅ Django shell tests pass  

---

## Next: Phase 2

Once Phase 1 is complete, move to **Phase 2: Async Execution & Integration**

- Create async_tasks.py
- Implement ThreadPoolExecutor job execution
- Refactor scrape.py into job_service.py
- Add error handling and logging
- Implement Prospects model integration

---

## Files to Create/Modify

```
apps/scraper/
├── models.py                    [CREATE]
├── forms.py                     [CREATE]
├── views.py                     [CREATE/UPDATE]
├── urls.py                      [UPDATE]
├── admin.py                     [UPDATE]
├── management/
│   └── commands/
│       └── load_county_urls.py  [CREATE]

config/urls.py                   [UPDATE - add scraper include]
apps/accounts/models.py          [UPDATE - add scraper_admin role]

.gitignore                        [UPDATE - add scraped_data/]
```

---

## Common Issues & Solutions

### Issue: LocationState/LocationCounty not found
**Solution**: Locations app must be migrated first
```bash
python manage.py migrate locations
```

### Issue: UUID import error
**Solution**: Add to models.py
```python
import uuid
```

### Issue: Migration conflicts
**Solution**: Check for existing scraper migrations
```bash
python manage.py showmigrations scraper
```

### Issue: Permission group not found
**Solution**: Create in Django shell
```python
from django.contrib.auth.models import Group, Permission
group = Group.objects.create(name='scraper_admin')
# Add permissions manually in admin
```

---

## Questions?

Refer back to [scraper_plan.md](scraper_plan.md) for detailed specifications.

Good luck! 🚀
