import threading
import json
from datetime import timedelta, date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView, View
from django.utils import timezone
from django.db.models import Q, Count, Sum, Max, Min
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.mixins import AdminRequiredMixin
from apps.locations.models import State

from .engine import run_scrape_job
from .forms import ScrapeJobForm, JobCreationForm, JobFilterForm
from .models import ScrapeJob, ScrapeLog, ScrapingJob, JobExecutionLog, JobError
from .services import (
    execute_job_async, get_job_status_polling, retry_failed_job,
    JobFilterService, CountyQueryService, JobCloneService,
    JobRetryCountService, JobStatusTransitionService,
    JobStatisticsService, JobExecutionService,
)


# ============================================================================
# PHASE 1: VIEWS FOR NEW SCRAPING JOB MANAGEMENT SYSTEM
# ============================================================================

class DashboardView(AdminRequiredMixin, TemplateView):
    """Dashboard showing job statistics and recent activity"""
    template_name = "scraper/dashboard.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Aggregate stats
        total_jobs = ScrapingJob.objects.filter(is_active=True).count()
        pending_jobs = ScrapingJob.objects.filter(status='pending', is_active=True).count()
        running_jobs = ScrapingJob.objects.filter(status='running', is_active=True).count()
        completed_jobs = ScrapingJob.objects.filter(status='completed', is_active=True).count()
        failed_jobs = ScrapingJob.objects.filter(status='failed', is_active=True).count()
        
        # Recent jobs
        recent_jobs = ScrapingJob.objects.filter(is_active=True).order_by('-created_at')[:10]
        
        # Recent errors
        recent_errors = JobError.objects.select_related('job').order_by('-created_at')[:10]
        
        # Jobs by state
        jobs_by_state = ScrapingJob.objects.filter(is_active=True).values('state').annotate(
            count=Count('id'),
            failed=Count('id', filter=Q(status='failed')),
            success=Count('id', filter=Q(status='completed'))
        )
        
        ctx.update({
            'total_jobs': total_jobs,
            'pending_jobs': pending_jobs,
            'running_jobs': running_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs,
            'recent_jobs': recent_jobs,
            'recent_errors': recent_errors,
            'jobs_by_state': jobs_by_state,
        })
        return ctx


class JobListView(AdminRequiredMixin, ListView):
    """List all scraping jobs with filtering"""
    model = ScrapingJob
    template_name = "scraper/job_list_v2.html"
    paginate_by = 20
    context_object_name = 'jobs'
    
    def get_queryset(self):
        qs = ScrapingJob.objects.filter(is_active=True).order_by('-created_at')
        
        # Apply filters
        form = JobFilterForm(self.request.GET or None)
        if form.is_valid():
            if form.cleaned_data.get('status'):
                qs = qs.filter(status=form.cleaned_data['status'])
            if form.cleaned_data.get('state'):
                state = form.cleaned_data['state']
                qs = qs.filter(state=state.abbreviation)
            if form.cleaned_data.get('county'):
                county = form.cleaned_data['county']
                qs = qs.filter(county=county.name)
            if form.cleaned_data.get('date_range_start'):
                qs = qs.filter(created_at__gte=form.cleaned_data['date_range_start'])
            if form.cleaned_data.get('date_range_end'):
                end_date = form.cleaned_data['date_range_end'] + timedelta(days=1)
                qs = qs.filter(created_at__lt=end_date)
        
        self.filtered_queryset = qs
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = JobFilterForm(self.request.GET or None)
        ctx['group_summaries'] = self.get_group_summaries()
        return ctx

    def get_group_summaries(self):
        qs = getattr(self, 'filtered_queryset', ScrapingJob.objects.none())

        summary = list(qs.values('group_name').annotate(
            total=Count('id'),
            running_jobs=Count('id', filter=Q(status='running')),
            failed_jobs=Count('id', filter=Q(status='failed')),
            completed_jobs=Count('id', filter=Q(status='completed')),
            pending_jobs=Count('id', filter=Q(status='pending')),
            success_rows=Sum('rows_success'),
            failed_rows=Sum('rows_failed'),
        ).order_by('group_name'))

        summaries = []
        for entry in summary:
            if entry['running_jobs'] > 0:
                status = 'running'
            elif entry['failed_jobs'] > 0:
                status = 'failed'
            elif entry['completed_jobs'] == entry['total'] and entry['total'] > 0:
                status = 'completed'
            else:
                status = 'pending'

            summaries.append({
                'group_name': entry['group_name'] or 'Ungrouped',
                'status': status,
                'success_count': entry['success_rows'] or 0,
                'failed_count': entry['failed_rows'] or 0,
                'total_jobs': entry['total'],
            })

        return summaries


class JobDetailView(AdminRequiredMixin, DetailView):
    """Show detailed job information"""
    model = ScrapingJob
    template_name = "scraper/job_detail.html"
    context_object_name = 'job'
    
    def get_queryset(self):
        return ScrapingJob.objects.filter(is_active=True)
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        job = self.object
        
        ctx['execution_logs'] = JobExecutionLog.objects.filter(
            job=job
        ).order_by('-started_at')[:20]
        
        ctx['errors'] = JobError.objects.filter(
            job=job
        ).order_by('-created_at')[:20]
        
        # Calculate stats
        total_errors = JobError.objects.filter(job=job).count()
        retryable_errors = JobError.objects.filter(job=job, is_retryable=True).count()
        
        ctx['total_errors'] = total_errors
        ctx['retryable_errors'] = retryable_errors
        
        return ctx


class JobCreateView(AdminRequiredMixin, CreateView):
    """Create a new scraping job"""
    model = ScrapingJob
    form_class = JobCreationForm
    template_name = "scraper/job_create.html"
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = 'pending'
        response = super().form_valid(form)
        messages.success(self.request, f'Job "{self.object.name}" created successfully.')
        return response
    
    def get_success_url(self):
        return reverse('scraper:job_detail_v2', kwargs={'pk': self.object.pk})


# ============================================================================
# PHASE 3: ADVANCED FEATURES - API ENDPOINTS
# ============================================================================

class JobCloneAPIView(AdminRequiredMixin, View):
    """Clone an existing job with optional date/name modifications"""
    
    def post(self, request, pk):
        """
        POST /api/v2/jobs/<pk>/clone/
        Body: {
            "name": "Optional new name",
            "date_shift_days": 7,
            "update_user_defaults": true
        }
        """
        try:
            job = get_object_or_404(ScrapingJob, pk=pk, is_active=True)
            
            # Parse request body
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON in request body'
                }, status=400)
            
            # Get clone parameters
            new_name = data.get('name', f"{job.name} (Clone)")
            date_shift_days = data.get('date_shift_days', 0)
            update_defaults = data.get('update_user_defaults', False)
            
            # Clone the job
            if date_shift_days != 0:
                from datetime import timedelta
                new_start = job.start_date + timedelta(days=date_shift_days)
                new_end = job.end_date + timedelta(days=date_shift_days)
                cloned_job = JobCloneService.clone_job(
                    source_job=job,
                    new_name=new_name,
                    new_start_date=new_start,
                    new_end_date=new_end
                )
            else:
                cloned_job = JobCloneService.clone_job(
                    source_job=job,
                    new_name=new_name
                )
            
            # Update user defaults if requested
            if update_defaults:
                from .services import UserDefaultsService
                UserDefaultsService.update_defaults(
                    user=request.user,
                    state=cloned_job.state,
                    county=cloned_job.county,
                    start_date=cloned_job.start_date,
                    end_date=cloned_job.end_date
                )
            
            return JsonResponse({
                'success': True,
                'message': f'Job cloned successfully',
                'job_id': str(cloned_job.pk),
                'job_name': cloned_job.name,
                'redirect_url': reverse('scraper:job_detail_v2', kwargs={'pk': cloned_job.pk})
            })
            
        except ScrapingJob.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Job not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error cloning job: {str(e)}'
            }, status=500)


class CountiesAjaxAPIView(AdminRequiredMixin, View):
    """Get counties for a given state (AJAX endpoint)"""
    
    def get(self, request, state_code):
        """
        GET /api/v2/counties/<state_code>/
        Returns: { "counties": [{"id": 1, "name": "County Name"}, ...] }
        """
        try:
            counties = CountyQueryService.get_counties_by_state(state_code)
            
            # counties is already a list of dicts from values('id', 'name')
            return JsonResponse({
                'success': True,
                'state': state_code,
                'counties': counties,
                'count': len(counties)
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error retrieving counties: {str(e)}'
            }, status=500)


class JobStatsAPIView(AdminRequiredMixin, View):
    """Get statistics for a job or all jobs"""
    
    def get(self, request, pk=None):
        """
        GET /api/v2/jobs/stats/ - All jobs stats
        GET /api/v2/jobs/<pk>/stats/ - Single job stats
        """
        try:
            if pk:
                # Single job stats
                job = get_object_or_404(ScrapingJob, pk=pk, is_active=True)
                
                exec_logs = JobExecutionLog.objects.filter(job=job)
                errors = JobError.objects.filter(job=job)
                
                success_count = exec_logs.filter(status='completed').count()
                failure_count = exec_logs.filter(status='failed').count()
                total_executions = exec_logs.count()
                
                success_rate = (success_count / total_executions * 100) if total_executions > 0 else 0
                
                stats = {
                    'job_id': str(job.pk),
                    'job_name': job.name,
                    'status': job.status,
                    'created_at': job.created_at.isoformat(),
                    'executions': total_executions,
                    'successful': success_count,
                    'failed': failure_count,
                    'success_rate': f"{success_rate:.1f}%",
                    'errors': [
                        {
                            'type': error.error_type,
                            'message': error.error_message,
                            'retryable': error.is_retryable,
                            'created_at': error.created_at.isoformat()
                        }
                        for error in errors[:10]
                    ]
                }
            else:
                # All jobs stats
                all_jobs = ScrapingJob.objects.filter(is_active=True)
                stats = JobStatisticsService.get_job_stats(all_jobs)
            
            return JsonResponse({
                'success': True,
                'stats': stats
            })
            
        except ScrapingJob.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Job not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error retrieving stats: {str(e)}'
            }, status=500)


class AdvancedFilterAPIView(AdminRequiredMixin, View):
    """Advanced filtering with complex parameters"""
    
    def post(self, request):
        """
        POST /api/v2/filter/
        Body: {
            "status": "completed",
            "state": "FL",
            "county": "Miami-Dade",
            "search": "insurance",
            "has_errors": false,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "sort_by": "-created_at",
            "page": 1,
            "per_page": 10
        }
        """
        try:
            # Parse request body
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON in request body'
                }, status=400)
            
            # Build filter dictionary
            filters = {}
            
            if data.get('status'):
                filters['status'] = data.get('status')
            
            if data.get('state'):
                filters['state'] = data.get('state')
            
            if data.get('county'):
                filters['county'] = data.get('county')
            
            if data.get('search'):
                filters['search'] = data.get('search')
            
            if data.get('has_errors') is not None:
                filters['has_errors'] = data.get('has_errors')
            
            if data.get('start_date') and data.get('end_date'):
                # Parse date strings to date objects
                from datetime import datetime
                filters['start_date'] = datetime.fromisoformat(data.get('start_date')).date()
                filters['end_date'] = datetime.fromisoformat(data.get('end_date')).date()
            
            # Add sort parameter (defaults to '-created_at' in apply_filters)
            if data.get('sort_by'):
                filters['sort'] = data.get('sort_by')
            
            # Apply filters
            queryset = JobFilterService.apply_filters(
                qs=ScrapingJob.objects.filter(is_active=True),
                filters=filters
            )
            
            # Pagination
            page = max(1, data.get('page', 1))
            per_page = min(100, data.get('per_page', 10))
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            total_count = queryset.count()
            jobs = queryset[start_idx:end_idx]
            
            # Build response
            job_list = []
            for job in jobs:
                job_list.append({
                    'id': str(job.pk),
                    'name': job.name,
                    'status': job.status,
                    'state': job.state if job.state else None,
                    'county': job.county.name if (job.county and hasattr(job.county, 'name')) else None,
                    'start_date': job.start_date.isoformat(),
                    'end_date': job.end_date.isoformat(),
                    'rows_scraped': getattr(job, 'total_rows_scraped', 0) or 0,
                    'created_at': job.created_at.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'results': job_list,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error applying filters: {str(e)}'
            }, status=500)




def _run_job_safe(job_pk):
    """Wrapper to run legacy ScrapeJob with fresh DB connection in thread."""
    from django.db import connection
    print("Running job in thread with job_pk:", job_pk)

    try:
        job = ScrapeJob.objects.select_related('county', 'county__state').get(pk=job_pk)
        run_scrape_job(job)
    except Exception as e:
        try:
            job = ScrapeJob.objects.get(pk=job_pk)
            if job.status != 'failed':
                job.status = 'failed'
                job.error_message = str(e)
                job.save()
        except Exception:
            pass
    finally:
        connection.close()


# ============================================================================
# LEGACY VIEWS: For ScrapeJob (Kept for backward compatibility)
# ============================================================================

class ScraperDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "scraper/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recent_jobs"] = ScrapeJob.objects.select_related("county", "triggered_by")[:10]
        ctx["running_jobs"] = ScrapeJob.objects.filter(status="running").count()
        ctx["total_jobs"] = ScrapeJob.objects.count()
        return ctx


class ScrapeJobListView(AdminRequiredMixin, ListView):
    model = ScrapeJob
    template_name = "scraper/job_list.html"
    paginate_by = 25

    def get_queryset(self):
        qs = ScrapeJob.objects.select_related("county", "county__state", "triggered_by")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        self.filtered_queryset = qs
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = ScrapeJob.JOB_STATUS
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["grouped_jobs"] = self.get_grouped_jobs()
        return ctx

    def get_grouped_jobs(self):
        qs = getattr(self, "filtered_queryset", ScrapeJob.objects.none())
        aggregated = qs.values("name").annotate(
            total_jobs=Count("id"),
            success_count=Count("id", filter=Q(status="completed")),
            failed_count=Count("id", filter=Q(status="failed")),
            running_count=Count("id", filter=Q(status="running")),
            pending_count=Count("id", filter=Q(status="pending")),
            latest_created=Max("created_at"),
            sample_job_id=Min("id"),
        ).order_by("name")

        grouped = []
        for entry in aggregated:
            if entry["running_count"]:
                status = "running"
            elif entry["failed_count"]:
                status = "failed"
            elif entry["success_count"] == entry["total_jobs"] and entry["total_jobs"] > 0:
                status = "completed"
            else:
                status = "pending"

            grouped.append({
                "name": entry["name"] or "Untitled Job",
                "status": status,
                "success_count": entry["success_count"],
                "failed_count": entry["failed_count"],
                "total_jobs": entry["total_jobs"],
                "latest_created": entry["latest_created"],
                "job_pk": entry["sample_job_id"],
            })

        return grouped


class ScrapeJobCreateView(AdminRequiredMixin, CreateView):
    model = ScrapeJob
    form_class = ScrapeJobForm
    template_name = "scraper/job_create.html"

    def form_valid(self, form):
        jobs = form.save_multiple(triggered_by=self.request.user)

        if len(jobs) == 1:
            job = jobs[0]
            messages.success(self.request, f"Scrape job #{job.pk} created.")
            return redirect("scraper:job_detail", pk=job.pk)

        messages.success(self.request, f"{len(jobs)} scrape jobs created.")
        return redirect("scraper:job_list")

    def get_success_url(self):
        return reverse("scraper:job_detail", kwargs={"pk": self.object.pk})


class ScrapeJobGroupDetailView(AdminRequiredMixin, TemplateView):
    template_name = "scraper/job_group_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.anchor_job = get_object_or_404(ScrapeJob, pk=kwargs.get("pk"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        group_name = self.anchor_job.name

        jobs = ScrapeJob.objects.filter(name=group_name).select_related(
            "county",
            "county__state",
            "triggered_by",
        ).order_by("county__name", "pk")
        first_job = jobs.first()

        summary = jobs.aggregate(
            total_jobs=Count("id"),
            success_count=Count("id", filter=Q(status="completed")),
            failed_count=Count("id", filter=Q(status="failed")),
            running_count=Count("id", filter=Q(status="running")),
            pending_count=Count("id", filter=Q(status="pending")),
            prospects_total=Sum("prospects_created"),
        )

        ctx.update({
            "group_name": group_name or "Untitled Job",
            "jobs": jobs,
            "first_job": first_job,
            "summary": summary,
        })
        return ctx


class ScrapeJobDetailView(AdminRequiredMixin, DetailView):
    model = ScrapeJob
    template_name = "scraper/job_detail.html"

    def get_queryset(self):
        return ScrapeJob.objects.select_related("county", "county__state", "triggered_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = ScrapeLog.objects.filter(job=self.object).order_by("-created_at")[:50]
        return ctx


class ScrapeJobRunView(AdminRequiredMixin, DetailView):
    """Run a pending/failed job in a background thread."""
    model = ScrapeJob

    def post(self, request, *args, **kwargs):
        print("job run view called")

        job = self.get_object()
        if job.status == "running":
            messages.warning(request, "Job is already running.")
            return redirect("scraper:job_detail", pk=job.pk)

        # Reset if re-running a failed job
        if job.status in ("failed", "completed"):
            job.status = "pending"
            job.error_message = ""
            job.prospects_created = 0
            job.prospects_updated = 0
            job.prospects_qualified = 0
            job.prospects_disqualified = 0
            job.save()

        # Run in background thread
        thread = threading.Thread(target=_run_job_safe, args=(job.pk,), daemon=True)
        thread.start()

        messages.success(request, f"Job #{job.pk} started in background.")
        return redirect("scraper:job_detail", pk=job.pk)


# ============================================================================
# PHASE 2: API ENDPOINTS FOR JOB STATUS POLLING & ASYNC EXECUTION
# ============================================================================

class JobExecuteAPIView(AdminRequiredMixin, View):
    """API endpoint to execute a job asynchronously"""
    
    def post(self, request, pk):
        """
        Execute a job asynchronously.
        
        Args:
            pk: UUID of the ScrapingJob
            
        Returns:
            JSON response with status
        """
        try:
            job = ScrapingJob.objects.get(id=pk)
            
            # Submit for async execution
            success = execute_job_async(str(job.id))
            
            if success:
                return JsonResponse({
                    'success': True,
                    'message': f'Job {job.name} submitted for execution',
                    'job_id': str(job.id),
                    'status_url': reverse('scraper:job_status_api', kwargs={'pk': job.id}),
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Job is already running or could not be submitted',
                }, status=400)
        
        except ScrapingJob.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Job not found',
            }, status=404)


class JobStatusAPIView(AdminRequiredMixin, View):
    """API endpoint to poll job status"""
    
    def get(self, request, pk):
        """
        Get current job status.
        
        Args:
            pk: UUID of the ScrapingJob
            
        Returns:
            JSON response with job status
        """
        try:
            status = get_job_status_polling(str(pk))
            
            if 'error' in status:
                return JsonResponse(status, status=404)
            
            return JsonResponse(status)
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
            }, status=500)


class JobRetryAPIView(AdminRequiredMixin, View):
    """API endpoint to retry a failed job"""
    
    def post(self, request, pk):
        """
        Retry a failed job.
        
        Args:
            pk: UUID of the ScrapingJob
            
        Returns:
            JSON response with result
        """
        try:
            job = ScrapingJob.objects.get(id=pk)
            
            if job.status != 'failed':
                return JsonResponse({
                    'success': False,
                    'error': f'Job status is {job.status}, not failed',
                }, status=400)
            
            success = retry_failed_job(str(job.id))
            
            if success:
                return JsonResponse({
                    'success': True,
                    'message': f'Job {job.name} submitted for retry',
                    'job_id': str(job.id),
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Job could not be retried (max retries reached?)',
                }, status=400)
        
        except ScrapingJob.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Job not found',
            }, status=404)

# ============================================================================
# COUNTY SCRAPE URL MANAGEMENT VIEWS
# ============================================================================

class CountyScrapeURLListView(AdminRequiredMixin, ListView):
    """List all county scrape URLs with search"""
    from .models import CountyScrapeURL
    model = CountyScrapeURL
    template_name = "scraper/countyscrapeurl_list.html"
    context_object_name = "scrape_urls"
    paginate_by = 20

    def get_queryset(self):
        qs = self.model.objects.select_related('county', 'state', 'updated_by').order_by('-updated_at')
        
        # Search by county name
        county_search = self.request.GET.get('county', '').strip()
        if county_search:
            qs = qs.filter(county__name__icontains=county_search)
        
        # Search by state
        state_search = self.request.GET.get('state', '').strip()
        if state_search:
            qs = qs.filter(state__name__icontains=state_search) | qs.filter(state__abbreviation__icontains=state_search)
        
        # Filter by URL type
        url_type = self.request.GET.get('url_type', '').strip()
        if url_type:
            qs = qs.filter(url_type=url_type)
        
        # Filter by active status
        is_active = self.request.GET.get('is_active', '').strip()
        if is_active:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['county_search'] = self.request.GET.get('county', '')
        ctx['state_search'] = self.request.GET.get('state', '')
        ctx['url_type_filter'] = self.request.GET.get('url_type', '')
        ctx['is_active_filter'] = self.request.GET.get('is_active', '')
        
        # Get unique states and URL types for filter dropdowns
        from .models import CountyScrapeURL
        ctx['states'] = State.objects.filter(is_active=True).order_by('name')
        ctx['url_types'] = CountyScrapeURL.URL_TYPE_CHOICES
        
        return ctx


class CountyScrapeURLCreateView(AdminRequiredMixin, CreateView):
    """Create a new county scrape URL"""
    from .models import CountyScrapeURL
    from .forms import CountyScrapeURLForm
    model = CountyScrapeURL
    form_class = CountyScrapeURLForm
    template_name = "scraper/countyscrapeurl_form.html"
    success_url = reverse_lazy("scraper:countyscrapeurl_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "County scrape URL created successfully.")
        return super().form_valid(form)


class CountyScrapeURLUpdateView(AdminRequiredMixin, UpdateView):
    """Update an existing county scrape URL"""
    from .models import CountyScrapeURL
    from .forms import CountyScrapeURLForm
    from django.views.generic import UpdateView
    model = CountyScrapeURL
    form_class = CountyScrapeURLForm
    template_name = "scraper/countyscrapeurl_form.html"
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy("scraper:countyscrapeurl_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "County scrape URL updated successfully.")
        return super().form_valid(form)


class CountyScrapeURLDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a county scrape URL"""
    from .models import CountyScrapeURL
    from django.views.generic import DeleteView
    model = CountyScrapeURL
    success_url = reverse_lazy("scraper:countyscrapeurl_list")
    pk_url_kwarg = 'pk'

    def delete(self, request, *args, **kwargs):
        messages.success(request, "County scrape URL deleted successfully.")
        return super().delete(request, *args, **kwargs)