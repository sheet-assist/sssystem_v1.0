"""
Scraper Services Package

Services for job execution, error handling, async tasks, filtering, and utilities.
"""

from .async_tasks import (
    JobExecutor,
    JobRetryManager,
    JobBatchProcessor,
    execute_job_async,
    get_job_status_polling,
    retry_failed_job,
)

from .error_handler import (
    ErrorHandler,
    ErrorRecoveryManager,
)

from .job_service import (
    AuctionScraper,
    JobExecutionService,
    ProspectConverter,
)

from .filter_service import (
    JobFilterService,
    JobStatisticsService,
    CountyQueryService,
    ProspectFilterService,
)

from .job_utils import (
    JobCloneService,
    JobDateService,
    UserDefaultsService,
    JobRetryCountService,
    JobStatusTransitionService,
    JobQualityMetricsService,
)

__all__ = [
    # Async tasks
    'JobExecutor',
    'JobRetryManager',
    'JobBatchProcessor',
    'execute_job_async',
    'get_job_status_polling',
    'retry_failed_job',
    # Error handling
    'ErrorHandler',
    'ErrorRecoveryManager',
    # Job execution
    'AuctionScraper',
    'JobExecutionService',
    'ProspectConverter',
    # Filtering
    'JobFilterService',
    'JobStatisticsService',
    'CountyQueryService',
    'ProspectFilterService',
    # Utilities
    'JobCloneService',
    'JobDateService',
    'UserDefaultsService',
    'JobRetryCountService',
    'JobStatusTransitionService',
    'JobQualityMetricsService',
]
