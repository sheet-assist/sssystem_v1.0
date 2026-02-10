"""
Asynchronous Task Execution Manager

Handles concurrent job execution using ThreadPoolExecutor.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from datetime import datetime

from django.utils import timezone
from django.db import transaction

from apps.scraper.models import ScrapingJob, JobExecutionLog, JobError
from .error_handler import ErrorHandler, ErrorRecoveryManager
from .job_service import JobExecutionService


# ============================================================================
# GLOBAL JOB EXECUTOR
# ============================================================================

class JobExecutor:
    """
    Manages concurrent scraper job execution using ThreadPoolExecutor.
    
    Usage:
        executor = JobExecutor(max_workers=4)
        executor.submit_job(job_id)
        executor.wait_for_completion()
    """
    
    # Global instance
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, max_workers: int = 4):
        """Singleton pattern for global executor"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize the job executor.
        
        Args:
            max_workers: Maximum concurrent jobs
        """
        if self._initialized:
            return
        
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='scraper-job')
        self.active_jobs = {}  # job_id -> Future
        self.job_results = {}  # job_id -> result
        self._lock = threading.Lock()
        self._initialized = True
    
    def submit_job(self, job_id: str) -> bool:
        """
        Submit a job for execution.
        
        Args:
            job_id: UUID of the ScrapingJob
            
        Returns:
            True if submitted, False if already running
        """
        try:
            job = ScrapingJob.objects.get(id=job_id)
        except ScrapingJob.DoesNotExist:
            return False
        
        with self._lock:
            if job_id in self.active_jobs:
                return False  # Already running
            
            # Submit job execution
            future = self.executor.submit(self._execute_job_wrapper, job_id)
            self.active_jobs[job_id] = future
        
        return True
    
    def _execute_job_wrapper(self, job_id: str):
        """
        Wrapper for job execution with proper Django DB handling.

        Args:
            job_id: UUID of the ScrapingJob
        """
        from django.db import connection

        try:
            job = ScrapingJob.objects.get(id=job_id)
            service = JobExecutionService(job)
            result = service.execute()

            with self._lock:
                self.job_results[job_id] = {
                    'success': True,
                    'result': result,
                    'timestamp': timezone.now(),
                }

        except Exception as e:
            with self._lock:
                self.job_results[job_id] = {
                    'success': False,
                    'error': str(e),
                    'timestamp': timezone.now(),
                }

        finally:
            with self._lock:
                if job_id in self.active_jobs:
                    del self.active_jobs[job_id]
            connection.close()
    
    def is_job_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        with self._lock:
            return job_id in self.active_jobs
    
    def get_job_status(self, job_id: str) -> Dict:
        """
        Get the status of a job.
        
        Args:
            job_id: UUID of the ScrapingJob
            
        Returns:
            Dictionary with status info
        """
        try:
            job = ScrapingJob.objects.get(id=job_id)
            is_running = self.is_job_running(job_id)
            
            result = {
                'job_id': str(job_id),
                'status': job.status,
                'is_running': is_running,
                'rows_processed': job.rows_processed,
                'rows_success': job.rows_success,
                'rows_failed': job.rows_failed,
                'created_at': job.created_at.isoformat(),
            }
            
            with self._lock:
                if job_id in self.job_results:
                    result['result'] = self.job_results[job_id]
            
            return result
        
        except ScrapingJob.DoesNotExist:
            return {'error': 'Job not found'}
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.
        
        Args:
            job_id: UUID of the ScrapingJob
            
        Returns:
            True if cancelled, False if not running
        """
        with self._lock:
            if job_id in self.active_jobs:
                future = self.active_jobs[job_id]
                cancelled = future.cancel()
                if cancelled:
                    del self.active_jobs[job_id]
                return cancelled
        
        return False
    
    def get_active_jobs(self) -> List[str]:
        """Get list of currently running job IDs"""
        with self._lock:
            return list(self.active_jobs.keys())
    
    def wait_for_completion(self, timeout: Optional[int] = None) -> Dict[str, Dict]:
        """
        Wait for all active jobs to complete.
        
        Args:
            timeout: Timeout in seconds (None for no timeout)
            
        Returns:
            Dictionary of job results
        """
        with self._lock:
            futures = dict(self.active_jobs)
        
        results = {}
        for job_id, future in futures.items():
            try:
                future.result(timeout=timeout)
                with self._lock:
                    if job_id in self.job_results:
                        results[job_id] = self.job_results[job_id]
            except Exception as e:
                results[job_id] = {
                    'success': False,
                    'error': str(e),
                }
        
        return results
    
    def shutdown(self, wait: bool = True):
        """Shutdown the executor"""
        self.executor.shutdown(wait=wait)


# ============================================================================
# JOB SCHEDULER & RETRY MANAGER
# ============================================================================

class JobRetryManager:
    """Manages job retry logic"""
    
    def __init__(self):
        """Initialize retry manager"""
        self.error_handler = ErrorHandler()
        self.executor = JobExecutor()
    
    def retry_failed_job(self, job_id: str) -> bool:
        """
        Retry a failed job.
        
        Args:
            job_id: UUID of the ScrapingJob
            
        Returns:
            True if retry submitted, False otherwise
        """
        try:
            job = ScrapingJob.objects.get(id=job_id)
            recovery_manager = ErrorRecoveryManager(job)
            
            can_retry, reason = recovery_manager.can_retry()
            if not can_retry:
                return False
            
            # Reset job status
            job.status = 'pending'
            job.save()
            
            # Submit for execution
            return self.executor.submit_job(job_id)
        
        except ScrapingJob.DoesNotExist:
            return False
    
    def auto_retry_failed_jobs(self) -> List[str]:
        """
        Automatically retry all eligible failed jobs.
        
        Returns:
            List of submitted job IDs
        """
        failed_jobs = ScrapingJob.objects.filter(status='failed', is_active=True)
        submitted = []
        
        for job in failed_jobs:
            recovery_manager = ErrorRecoveryManager(job)
            can_retry, _reason = recovery_manager.can_retry()
            
            if can_retry:
                if self.retry_failed_job(str(job.id)):
                    submitted.append(str(job.id))
        
        return submitted


# ============================================================================
# JOB BATCH PROCESSOR
# ============================================================================

class JobBatchProcessor:
    """Processes multiple jobs in batches"""
    
    def __init__(self, batch_size: int = 10):
        """
        Initialize batch processor.
        
        Args:
            batch_size: Number of jobs per batch
        """
        self.batch_size = batch_size
        self.executor = JobExecutor()
    
    def process_pending_jobs(self, limit: Optional[int] = None) -> Dict:
        """
        Process all pending jobs.
        
        Args:
            limit: Maximum number of jobs to process (None for all)
            
        Returns:
            Dictionary with processing results
        """
        pending_jobs = ScrapingJob.objects.filter(
            status='pending',
            is_active=True
        ).order_by('created_at')
        
        if limit:
            pending_jobs = pending_jobs[:limit]
        
        submitted = []
        for job in pending_jobs:
            if self.executor.submit_job(str(job.id)):
                submitted.append(str(job.id))
        
        return {
            'submitted': len(submitted),
            'job_ids': submitted,
        }
    
    def wait_and_report(self, timeout: Optional[int] = None) -> Dict:
        """
        Wait for all jobs and return results.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Dictionary with results and statistics
        """
        results = self.executor.wait_for_completion(timeout=timeout)
        
        successful = sum(1 for r in results.values() if r.get('success'))
        failed = len(results) - successful
        
        return {
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'results': results,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def execute_job_async(job_id: str) -> bool:
    """
    Execute a job asynchronously.
    
    Args:
        job_id: UUID of the ScrapingJob
        
    Returns:
        True if submitted, False otherwise
    """
    executor = JobExecutor()
    return executor.submit_job(job_id)


def get_job_status_polling(job_id: str) -> Dict:
    """
    Get the status of a job (for polling API).
    
    Args:
        job_id: UUID of the ScrapingJob
        
    Returns:
        Dictionary with status information
    """
    executor = JobExecutor()
    return executor.get_job_status(job_id)


def retry_failed_job(job_id: str) -> bool:
    """
    Retry a failed job.
    
    Args:
        job_id: UUID of the ScrapingJob
        
    Returns:
        True if retry submitted
    """
    manager = JobRetryManager()
    return manager.retry_failed_job(job_id)
