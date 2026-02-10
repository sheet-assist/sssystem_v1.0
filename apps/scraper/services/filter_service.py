"""
Advanced Filtering Service for Scraper Jobs

Provides complex filtering, searching, and querying capabilities.
"""

from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional
from django.db.models import Q, QuerySet, Sum

from apps.scraper.models import ScrapingJob, JobError
from apps.locations.models import State, County


class JobFilterService:
    """Advanced filtering for ScrapingJob queryset"""
    
    def __init__(self):
        """Initialize filter service"""
        pass
    
    @staticmethod
    def filter_by_status(qs: QuerySet, status: str) -> QuerySet:
        """Filter jobs by status"""
        if status and status != 'all':
            qs = qs.filter(status=status)
        return qs
    
    @staticmethod
    def filter_by_state(qs: QuerySet, state: str) -> QuerySet:
        """Filter jobs by state code"""
        if state:
            qs = qs.filter(state=state)
        return qs
    
    @staticmethod
    def filter_by_county(qs: QuerySet, county: str) -> QuerySet:
        """Filter jobs by county name"""
        if county:
            qs = qs.filter(county__name__icontains=county)
        return qs
    
    @staticmethod
    def filter_by_date_range(
        qs: QuerySet,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> QuerySet:
        """Filter jobs by creation date range"""
        if start_date:
            qs = qs.filter(created_at__gte=datetime.combine(start_date, datetime.min.time()))
        if end_date:
            qs = qs.filter(created_at__lte=datetime.combine(end_date, datetime.max.time()))
        return qs
    
    @staticmethod
    def filter_by_user(qs: QuerySet, user) -> QuerySet:
        """Filter jobs by creator user"""
        if user:
            qs = qs.filter(created_by=user)
        return qs
    
    @staticmethod
    def filter_by_name_search(qs: QuerySet, search_term: str) -> QuerySet:
        """Filter jobs by name search (case-insensitive)"""
        if search_term:
            qs = qs.filter(name__icontains=search_term)
        return qs
    
    @staticmethod
    def filter_by_error_status(qs: QuerySet, has_errors: bool) -> QuerySet:
        """Filter jobs with or without errors"""
        if has_errors:
            qs = qs.filter(errors__isnull=False).distinct()
        else:
            qs = qs.exclude(errors__isnull=False).distinct()
        return qs
    
    @staticmethod
    def sort_by(qs: QuerySet, sort_field: str = '-created_at') -> QuerySet:
        """Sort jobs by field"""
        valid_fields = [
            'created_at', '-created_at',
            'updated_at', '-updated_at',
            'name', '-name',
            'status', '-status',
            'rows_processed', '-rows_processed',
        ]
        
        if sort_field in valid_fields:
            qs = qs.order_by(sort_field)
        else:
            qs = qs.order_by('-created_at')
        
        return qs
    
    @staticmethod
    def apply_filters(
        qs: QuerySet,
        filters: Dict
    ) -> QuerySet:
        """
        Apply all filters at once.
        
        Args:
            qs: Queryset to filter
            filters: Dictionary with filter parameters:
                {
                    'status': 'pending',
                    'state': 'FL',
                    'county': 'Miami-Dade',
                    'start_date': date(2026, 2, 1),
                    'end_date': date(2026, 2, 10),
                    'search': 'job name',
                    'has_errors': True,
                    'created_by': user,
                    'sort': '-created_at',
                }
        
        Returns:
            Filtered queryset
        """
        qs = JobFilterService.filter_by_status(qs, filters.get('status'))
        qs = JobFilterService.filter_by_state(qs, filters.get('state'))
        qs = JobFilterService.filter_by_county(qs, filters.get('county'))
        qs = JobFilterService.filter_by_date_range(
            qs,
            filters.get('start_date'),
            filters.get('end_date')
        )
        qs = JobFilterService.filter_by_user(qs, filters.get('created_by'))
        qs = JobFilterService.filter_by_name_search(qs, filters.get('search'))
        
        if filters.get('has_errors') is not None:
            qs = JobFilterService.filter_by_error_status(qs, filters.get('has_errors'))
        
        qs = JobFilterService.sort_by(qs, filters.get('sort', '-created_at'))
        
        return qs


class JobStatisticsService:
    """Generate statistics and metrics for jobs"""
    
    @staticmethod
    def get_job_stats(qs: QuerySet) -> Dict:
        """
        Get overall statistics for a job queryset.
        
        Args:
            qs: Queryset of ScrapingJob
            
        Returns:
            Dictionary with statistics
        """
        total = qs.count()
        
        status_breakdown = {}
        for status in ['pending', 'running', 'completed', 'failed']:
            status_breakdown[status] = qs.filter(status=status).count()
        
        total_rows = qs.aggregate(
            total=Sum('rows_processed'),
            success=Sum('rows_success'),
            failed=Sum('rows_failed'),
        )
        
        return {
            'total_jobs': total,
            'status_breakdown': status_breakdown,
            'total_rows_processed': total_rows.get('total', 0) or 0,
            'total_rows_success': total_rows.get('success', 0) or 0,
            'total_rows_failed': total_rows.get('failed', 0) or 0,
            'completion_rate': (
                (status_breakdown.get('completed', 0) / total * 100)
                if total > 0 else 0
            ),
            'success_rate': (
                (total_rows.get('success', 0) / total_rows.get('total', 1) * 100)
                if total_rows.get('total', 0) > 0 else 0
            ),
        }
    
    @staticmethod
    def get_job_stats_by_state(qs: QuerySet) -> List[Dict]:
        """Get statistics broken down by state"""
        from django.db.models import Sum, Count
        
        states_data = qs.values('state').annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            rows=Sum('rows_processed'),
        ).order_by('-total')
        
        return list(states_data)
    
    @staticmethod
    def get_recent_errors(qs: QuerySet, limit: int = 10) -> List[Dict]:
        """Get recent errors for jobs in queryset"""
        job_ids = qs.values_list('id', flat=True)
        errors = JobError.objects.filter(
            job_id__in=job_ids
        ).select_related('job').order_by('-created_at')[:limit]
        
        return [
            {
                'job_name': error.job.name,
                'error_type': error.error_type,
                'error_message': error.error_message[:100],
                'is_retryable': error.is_retryable,
                'created_at': error.created_at,
            }
            for error in errors
        ]
    
    @staticmethod
    def get_success_metrics(qs: QuerySet) -> Dict:
        """Calculate success/failure metrics"""
        completed = qs.filter(status='completed').count()
        failed = qs.filter(status='failed').count()
        total = qs.count()
        
        return {
            'completed': completed,
            'failed': failed,
            'total': total,
            'success_percentage': (completed / total * 100) if total > 0 else 0,
            'failure_percentage': (failed / total * 100) if total > 0 else 0,
        }
    
    @staticmethod
    def get_timeline_data(qs: QuerySet, days: int = 30) -> List[Dict]:
        """Get job creation timeline for the past N days"""
        from django.db.models import Count
        
        timeline = qs.extra(
            select={'date': 'DATE(created_at)'}
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        return [
            {
                'date': item['date'].isoformat(),
                'count': item['count'],
            }
            for item in timeline
        ]


class CountyQueryService:
    """Service for querying counties by state"""
    
    @staticmethod
    def get_counties_by_state(state_code: str) -> List[Dict]:
        """
        Get all active counties for a state.
        
        Args:
            state_code: State abbreviation (e.g., 'FL')
            
        Returns:
            List of dicts with county id and name
        """
        try:
            state = State.objects.get(abbreviation=state_code)
            counties = County.objects.filter(
                state=state,
                is_active=True
            ).order_by('name').values('id', 'name')
            
            return list(counties)
        except State.DoesNotExist:
            return []
    
    @staticmethod
    def get_all_states() -> List[Dict]:
        """
        Get all active states.
        
        Returns:
            List of dicts with state abbreviation and name
        """
        states = State.objects.filter(
            is_active=True
        ).order_by('name').values('abbreviation', 'name')
        
        return list(states)
    
    @staticmethod
    def get_county_by_id(county_id: int) -> Optional[Dict]:
        """Get county details by ID"""
        try:
            county = County.objects.get(id=county_id)
            return {
                'id': county.id,
                'name': county.name,
                'state': county.state.abbreviation,
            }
        except County.DoesNotExist:
            return None
