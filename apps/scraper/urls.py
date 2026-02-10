from django.urls import path

from . import views

app_name = "scraper"

urlpatterns = [
    # ====================================================================
    # PHASE 1: NEW JOB MANAGEMENT ROUTES
    # ====================================================================
    
    # Dashboard
    path("", views.DashboardView.as_view(), name="dashboard_v2"),
    
    # New Job Management (ScrapingJob with UUID)
    path("v2/jobs/", views.JobListView.as_view(), name="job_list_v2"),
    path("v2/jobs/create/", views.JobCreateView.as_view(), name="job_create_v2"),
    path("v2/jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job_detail_v2"),
    
    # ====================================================================
    # PHASE 2: API ENDPOINTS FOR ASYNC EXECUTION & STATUS POLLING
    # ====================================================================
    
    path("api/v2/jobs/<uuid:pk>/execute/", views.JobExecuteAPIView.as_view(), name="job_execute_api"),
    path("api/v2/jobs/<uuid:pk>/status/", views.JobStatusAPIView.as_view(), name="job_status_api"),
    path("api/v2/jobs/<uuid:pk>/retry/", views.JobRetryAPIView.as_view(), name="job_retry_api"),
    
    # ====================================================================
    # PHASE 3: ADVANCED FEATURES - FILTERING, CLONING, STATISTICS
    # ====================================================================
    
    path("api/v2/jobs/<uuid:pk>/clone/", views.JobCloneAPIView.as_view(), name="job_clone_api"),
    path("api/v2/counties/<str:state_code>/", views.CountiesAjaxAPIView.as_view(), name="counties_ajax_api"),
    path("api/v2/jobs/<uuid:pk>/stats/", views.JobStatsAPIView.as_view(), name="job_stats_api"),
    path("api/v2/jobs/stats/", views.JobStatsAPIView.as_view(), name="all_jobs_stats_api"),
    path("api/v2/filter/", views.AdvancedFilterAPIView.as_view(), name="advanced_filter_api"),
    
    # ====================================================================
    # LEGACY ROUTES: Original ScrapeJob system (backward compatible)
    # ====================================================================
    
    path("dashboard/", views.ScraperDashboardView.as_view(), name="dashboard"),
    path("jobs/", views.ScrapeJobListView.as_view(), name="job_list"),
    path("jobs/create/", views.ScrapeJobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/", views.ScrapeJobDetailView.as_view(), name="job_detail"),
    path("jobs/<int:pk>/run/", views.ScrapeJobRunView.as_view(), name="job_run"),

    # ====================================================================
    # COUNTY SCRAPE URL MANAGEMENT
    # ====================================================================
    
    path("county-urls/", views.CountyScrapeURLListView.as_view(), name="countyscrapeurl_list"),
    path("county-urls/add/", views.CountyScrapeURLCreateView.as_view(), name="countyscrapeurl_add"),
    path("county-urls/<int:pk>/edit/", views.CountyScrapeURLUpdateView.as_view(), name="countyscrapeurl_edit"),
    path("county-urls/<int:pk>/delete/", views.CountyScrapeURLDeleteView.as_view(), name="countyscrapeurl_delete"),
]
