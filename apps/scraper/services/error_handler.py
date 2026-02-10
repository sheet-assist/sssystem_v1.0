"""
Error Handling Service for Scraper Jobs

Handles error categorization, retry logic, and error logging.
"""

import traceback
import threading
from typing import Tuple, Dict, Optional
from datetime import datetime, timedelta

from apps.scraper.models import JobError, JobExecutionLog


class ErrorHandler:
    """Handles job errors, categorization, and retry logic"""
    
    # Error categorization rules
    ERROR_PATTERNS = {
        'Network': [
            'Connection',
            'Timeout',
            'ConnectionError',
            'HTTPError',
            'RequestException',
            'socket.error',
            'urlopen',
        ],
        'Parsing': [
            'ParseError',
            'SyntaxError',
            'AttributeError',
            'KeyError',
            'IndexError',
            'BeautifulSoup',
            'selector',
        ],
        'DataValidation': [
            'ValidationError',
            'ValueError',
            'TypeError',
            'IntegrityError',
            'DataError',
        ],
        'System': [
            'SystemError',
            'MemoryError',
            'RuntimeError',
            'Exception',
        ]
    }
    
    # Errors that should NOT be retried
    NON_RETRYABLE = [
        'ValidationError',
        'DataError',
        'IntegrityError',
        'PermissionDenied',
    ]
    
    # Retry configuration (exponential backoff)
    RETRY_CONFIG = {
        'max_attempts': 3,
        'backoff_seconds': [5, 25, 125],  # 5s, 25s, 125s
    }
    
    @classmethod
    def categorize_error(cls, exception: Exception) -> str:
        """
        Categorize an exception into error types.
        
        Args:
            exception: The exception to categorize
            
        Returns:
            Error type string (Network, Parsing, DataValidation, System)
        """
        error_str = str(exception)
        exception_type = type(exception).__name__
        
        # Check by exception type first
        for error_type, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern in exception_type:
                    return error_type
        
        # Check by error message patterns
        for error_type, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in error_str.lower():
                    return error_type
        
        # Default to System error
        return 'System'
    
    @classmethod
    def is_retryable(cls, exception: Exception) -> bool:
        """
        Determine if an error should trigger a retry.
        
        Args:
            exception: The exception to check
            
        Returns:
            True if should be retried, False otherwise
        """
        exception_type = type(exception).__name__
        
        # Check non-retryable list
        for non_retryable in cls.NON_RETRYABLE:
            if non_retryable in exception_type:
                return False
        
        # Network and Parsing errors are retryable
        error_type = cls.categorize_error(exception)
        if error_type in ['Network', 'Parsing']:
            return True
        
        return False
    
    @classmethod
    def log_error(
        cls,
        job,
        exception: Exception,
        execution_log: Optional[JobExecutionLog] = None,
        retry_attempt: int = 0,
    ) -> JobError:
        """
        Log an error to the database.
        
        Args:
            job: ScrapingJob instance
            exception: The exception that occurred
            execution_log: Related JobExecutionLog (if any)
            retry_attempt: Current retry attempt number
            
        Returns:
            Created JobError instance
        """
        error_type = cls.categorize_error(exception)
        is_retryable = cls.is_retryable(exception)
        
        error = JobError.objects.create(
            job=job,
            execution_log=execution_log,
            error_type=error_type,
            error_message=str(exception),
            error_traceback=traceback.format_exc(),
            is_retryable=is_retryable,
            retry_attempt=retry_attempt,
        )
        
        return error
    
    @classmethod
    def get_retry_delay(cls, attempt_number: int) -> int:
        """
        Get the delay in seconds before next retry.
        
        Args:
            attempt_number: Current retry attempt (0-indexed)
            
        Returns:
            Delay in seconds
        """
        if attempt_number >= len(cls.RETRY_CONFIG['backoff_seconds']):
            return cls.RETRY_CONFIG['backoff_seconds'][-1]
        return cls.RETRY_CONFIG['backoff_seconds'][attempt_number]
    
    @classmethod
    def should_retry(
        cls,
        job,
        exception: Exception,
        retry_attempt: int = 0
    ) -> bool:
        """
        Determine if job should be retried.
        
        Args:
            job: ScrapingJob instance
            exception: The exception that occurred
            retry_attempt: Current retry attempt number
            
        Returns:
            True if should retry, False otherwise
        """
        # Check max attempts
        if retry_attempt >= cls.RETRY_CONFIG['max_attempts']:
            return False
        
        # Check if error is retryable
        if not cls.is_retryable(exception):
            return False
        
        return True


class ErrorRecoveryManager:
    """Manages error recovery and retry workflows"""
    
    def __init__(self, job):
        """
        Initialize recovery manager.
        
        Args:
            job: ScrapingJob instance
        """
        self.job = job
        self.handler = ErrorHandler()
    
    def get_error_summary(self) -> Dict:
        """
        Get summary of errors for this job.
        
        Returns:
            Dictionary with error statistics
        """
        errors = JobError.objects.filter(job=self.job)
        
        error_types = {}
        for error_type in ['Network', 'Parsing', 'DataValidation', 'System']:
            count = errors.filter(error_type=error_type).count()
            error_types[error_type] = count
        
        retryable = errors.filter(is_retryable=True).count()
        non_retryable = errors.filter(is_retryable=False).count()
        
        return {
            'total_errors': errors.count(),
            'by_type': error_types,
            'retryable': retryable,
            'non_retryable': non_retryable,
        }
    
    def get_last_error(self) -> Optional[JobError]:
        """Get the most recent error for this job"""
        return JobError.objects.filter(job=self.job).order_by('-created_at').first()
    
    def can_retry(self) -> Tuple[bool, str]:
        """
        Check if job can be retried.
        
        Returns:
            Tuple of (can_retry: bool, reason: str)
        """
        last_error = self.get_last_error()
        if not last_error:
            return True, "No errors found"
        
        if last_error.retry_attempt >= self.handler.RETRY_CONFIG['max_attempts']:
            return False, f"Max retries ({self.handler.RETRY_CONFIG['max_attempts']}) exceeded"
        
        if not last_error.is_retryable:
            return False, "Last error is not retryable"
        
        return True, "Ready to retry"
