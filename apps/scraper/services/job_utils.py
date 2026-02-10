"""
Job Utilities Service

Handles job cloning, duplication, and utility operations.
"""

from datetime import datetime, timedelta, date
from typing import Dict, Tuple, Optional
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth.models import User

from apps.scraper.models import ScrapingJob, UserJobDefaults


class JobCloneService:
    """Service for cloning existing jobs"""
    
    @staticmethod
    def clone_job(
        source_job: ScrapingJob,
        new_name: Optional[str] = None,
        new_start_date: Optional[date] = None,
        new_end_date: Optional[date] = None,
        preserve_params: bool = True,
    ) -> ScrapingJob:
        """
        Clone an existing job with optional modifications.
        
        Args:
            source_job: ScrapingJob to clone
            new_name: Optional new job name (defaults to "Clone of {original}")
            new_start_date: Optional new start date
            new_end_date: Optional new end date
            preserve_params: Whether to copy custom_params
            
        Returns:
            New ScrapingJob instance
        """
        cloned_job = ScrapingJob.objects.create(
            name=new_name or f"Clone of {source_job.name}",
            state=source_job.state,
            county=source_job.county,
            start_date=new_start_date or source_job.start_date,
            end_date=new_end_date or source_job.end_date,
            created_by=source_job.created_by,
            status='pending',
            custom_params=source_job.custom_params if preserve_params else {},
            is_active=True,
        )
        
        return cloned_job
    
    @staticmethod
    def clone_with_date_shift(
        source_job: ScrapingJob,
        days_offset: int = 0,
        created_by: Optional[User] = None,
    ) -> ScrapingJob:
        """
        Clone a job with dates shifted by N days.
        
        Args:
            source_job: ScrapingJob to clone
            days_offset: Number of days to shift dates forward
            created_by: User creating the clone (defaults to original creator)
            
        Returns:
            New ScrapingJob with shifted dates
        """
        new_start = source_job.start_date + timedelta(days=days_offset)
        new_end = source_job.end_date + timedelta(days=days_offset)
        
        return JobCloneService.clone_job(
            source_job=source_job,
            new_name=f"{source_job.name} (+{days_offset}d)",
            new_start_date=new_start,
            new_end_date=new_end,
            preserve_params=True,
        )
    
    @staticmethod
    def clone_for_next_week(source_job: ScrapingJob) -> ScrapingJob:
        """Clone a job for the next 7 days"""
        return JobCloneService.clone_with_date_shift(source_job, days_offset=7)
    
    @staticmethod
    def batch_clone_for_range(
        source_job: ScrapingJob,
        start_date: date,
        end_date: date,
        interval_days: int = 7,
    ) -> list:
        """
        Create multiple clones with different date ranges.
        
        Args:
            source_job: Job to clone
            start_date: First clone start date
            end_date: Range end (last clone should cover this)
            interval_days: Days between clones (e.g., 7 for weekly)
            
        Returns:
            List of created cloned jobs
        """
        clones = []
        current_start = start_date
        
        while current_start < end_date:
            current_end = min(
                current_start + timedelta(days=interval_days - 1),
                end_date
            )
            
            clone = JobCloneService.clone_job(
                source_job=source_job,
                new_name=f"{source_job.name} ({current_start.isoformat()})",
                new_start_date=current_start,
                new_end_date=current_end,
                preserve_params=True,
            )
            clones.append(clone)
            
            current_start = current_end + timedelta(days=1)
        
        return clones


class JobDateService:
    """Service for date-related job operations"""
    
    @staticmethod
    def get_today() -> date:
        """Get today's date"""
        return timezone.now().date()
    
    @staticmethod
    def get_suggested_date_range(days: int = 7) -> Tuple[date, date]:
        """
        Get suggested date range (today to today+N days).
        
        Args:
            days: Number of days in range
            
        Returns:
            Tuple of (start_date, end_date)
        """
        today = JobDateService.get_today()
        end_date = today + timedelta(days=days - 1)
        
        return (today, end_date)
    
    @staticmethod
    def get_last_week_range() -> Tuple[date, date]:
        """Get last week's date range"""
        today = JobDateService.get_today()
        start = today - timedelta(days=7)
        return (start, today)
    
    @staticmethod
    def get_last_month_range() -> Tuple[date, date]:
        """Get last month's date range"""
        today = JobDateService.get_today()
        start = today - timedelta(days=30)
        return (start, today)
    
    @staticmethod
    def validate_date_range(
        start_date: date,
        end_date: date,
        max_days: int = 365,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            max_days: Maximum allowed days in range
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check start is before end
        if start_date > end_date:
            return False, "Start date must be before end date"
        
        # Check range doesn't exceed max
        delta = (end_date - start_date).days
        if delta > max_days:
            return False, f"Date range cannot exceed {max_days} days"
        
        # Check dates are not in the future
        today = JobDateService.get_today()
        if start_date > today:
            return False, "Start date cannot be in the future"
        
        return True, None


class UserDefaultsService:
    """Service for managing user job defaults"""
    
    @staticmethod
    def get_or_create_defaults(user: User) -> UserJobDefaults:
        """
        Get or create user defaults.
        
        Args:
            user: User instance
            
        Returns:
            UserJobDefaults instance
        """
        defaults, _created = UserJobDefaults.objects.get_or_create(user=user)
        return defaults
    
    @staticmethod
    def update_defaults(
        user: User,
        state=None,
        county=None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        custom_params: Optional[Dict] = None,
    ) -> UserJobDefaults:
        """
        Update user defaults.
        
        Args:
            user: User instance
            state: Default state
            county: Default county
            start_date: Last used start date
            end_date: Last used end date
            custom_params: Last used custom parameters
            
        Returns:
            Updated UserJobDefaults
        """
        defaults = UserDefaultsService.get_or_create_defaults(user)
        
        if state:
            defaults.default_state = state
        if county:
            defaults.default_county = county
        if start_date:
            defaults.last_start_date = start_date
        if end_date:
            defaults.last_end_date = end_date
        if custom_params is not None:
            defaults.last_custom_params = custom_params
        
        defaults.updated_at = timezone.now()
        defaults.save()
        
        return defaults
    
    @staticmethod
    def get_default_date_range(user: User) -> Tuple[Optional[date], Optional[date]]:
        """
        Get user's last used date range or suggested range.
        
        Args:
            user: User instance
            
        Returns:
            Tuple of (start_date, end_date) or (None, None) if no defaults
        """
        defaults = UserDefaultsService.get_or_create_defaults(user)
        
        if defaults.last_start_date and defaults.last_end_date:
            return (defaults.last_start_date, defaults.last_end_date)
        
        # Return suggested range
        today, end = JobDateService.get_suggested_date_range()
        return (today, end)


class JobRetryCountService:
    """Service for tracking and limiting retries"""
    
    MAX_RETRIES = 3
    
    @staticmethod
    def get_retry_count(job: ScrapingJob) -> int:
        """
        Get how many times a job has been retried.
        
        Args:
            job: ScrapingJob instance
            
        Returns:
            Number of retry attempts
        """
        from apps.scraper.models import JobError
        
        error_count = JobError.objects.filter(job=job).count()
        return error_count
    
    @staticmethod
    def can_retry(job: ScrapingJob) -> Tuple[bool, str]:
        """
        Check if a job can be retried.
        
        Args:
            job: ScrapingJob instance
            
        Returns:
            Tuple of (can_retry, reason)
        """
        retry_count = JobRetryCountService.get_retry_count(job)
        
        if retry_count >= JobRetryCountService.MAX_RETRIES:
            return False, f"Max retries ({JobRetryCountService.MAX_RETRIES}) reached"
        
        if job.status != 'failed':
            return False, f"Job status is {job.status}, not failed"
        
        return True, "Ready for retry"
    
    @staticmethod
    def get_next_retry_number(job: ScrapingJob) -> int:
        """Get the next retry attempt number"""
        return JobRetryCountService.get_retry_count(job) + 1
    
    @staticmethod
    def get_remaining_retries(job: ScrapingJob) -> int:
        """Get how many retries remain"""
        current = JobRetryCountService.get_retry_count(job)
        remaining = max(0, JobRetryCountService.MAX_RETRIES - current)
        return remaining


class JobStatusTransitionService:
    """Service for managing job status transitions"""
    
    VALID_TRANSITIONS = {
        'pending': ['running', 'failed'],
        'running': ['completed', 'failed'],
        'completed': ['pending'],  # Can restart
        'failed': ['pending'],  # Can retry
    }
    
    @staticmethod
    def can_transition(job: ScrapingJob, new_status: str) -> Tuple[bool, str]:
        """
        Check if job can transition to new status.
        
        Args:
            job: ScrapingJob instance
            new_status: Target status
            
        Returns:
            Tuple of (can_transition, reason)
        """
        current_status = job.status
        
        # Check if status is valid
        if new_status not in ['pending', 'running', 'completed', 'failed']:
            return False, f"Invalid status: {new_status}"
        
        # Get valid target statuses
        valid_targets = JobStatusTransitionService.VALID_TRANSITIONS.get(
            current_status,
            []
        )
        
        if new_status not in valid_targets:
            return False, f"Cannot transition from {current_status} to {new_status}"
        
        return True, "Valid transition"
    
    @staticmethod
    def transition_job(job: ScrapingJob, new_status: str) -> Tuple[bool, str]:
        """
        Attempt to transition job to new status.
        
        Args:
            job: ScrapingJob instance
            new_status: Target status
            
        Returns:
            Tuple of (success, message)
        """
        can_transition, reason = JobStatusTransitionService.can_transition(
            job,
            new_status
        )
        
        if not can_transition:
            return False, reason
        
        job.status = new_status
        job.updated_at = timezone.now()
        
        # Update timestamps
        if new_status == 'running':
            # Don't overwrite if already started
            if not job.start_date:
                job.start_date = timezone.now()
        elif new_status in ['completed', 'failed']:
            # Already has timestamps from execution
            pass
        
        job.save()
        return True, f"Job transitioned to {new_status}"


class JobQualityMetricsService:
    """Service for calculating job quality metrics"""
    
    @staticmethod
    def calculate_success_rate(job: ScrapingJob) -> float:
        """
        Calculate success rate of processed rows.
        
        Args:
            job: ScrapingJob instance
            
        Returns:
            Percentage (0-100)
        """
        if job.rows_processed == 0:
            return 0.0
        
        return (job.rows_success / job.rows_processed) * 100
    
    @staticmethod
    def calculate_failure_rate(job: ScrapingJob) -> float:
        """Calculate failure rate of processed rows"""
        if job.rows_processed == 0:
            return 0.0
        
        return (job.rows_failed / job.rows_processed) * 100
    
    @staticmethod
    def get_job_health(job: ScrapingJob) -> str:
        """
        Get overall health status of a job.
        
        Args:
            job: ScrapingJob instance
            
        Returns:
            Health status: 'excellent', 'good', 'fair', 'poor'
        """
        if job.status == 'failed':
            return 'poor'
        
        if job.rows_processed == 0:
            return 'fair'
        
        success_rate = JobQualityMetricsService.calculate_success_rate(job)
        
        if success_rate >= 95:
            return 'excellent'
        elif success_rate >= 80:
            return 'good'
        elif success_rate >= 60:
            return 'fair'
        else:
            return 'poor'
