# Fix: "You cannot call this from an async context" Error

## Root Cause Analysis

The error occurs in the **legacy flow** when clicking "Run Now" / "Re-run" on the job detail page:

1. Template POSTs to `scraper:job_run` -> `ScrapeJobRunView.post()`
2. `ScrapeJobRunView` spawns `threading.Thread(target=_run_job_safe, args=(job.pk,))`
3. `_run_job_safe` is a **stub** (TODO comments, never calls the real scraper engine)
4. The **real engine** (`engine.py:run_scrape_job`) uses `playwright.sync_api.sync_playwright()` which internally runs an async event loop
5. When Playwright's `sync_playwright()` detects it's being called from a context that already has a running asyncio event loop (inherited or leaked in the thread), it raises: *"You cannot call this from an async context - use a thread or sync_to_async"*

Additionally, the **new v2 flow** (`JobExecuteAPIView` -> `execute_job_async` -> `JobExecutor`) has the same issue: `JobExecutionService.execute()` calls `AuctionScraper.scrape_date_range()` which also uses `sync_playwright()` -- same problem.

**Core issue**: Playwright's `sync_playwright()` cannot run when an asyncio event loop is already active in the same thread. Neither `threading.Thread` nor `ThreadPoolExecutor` guarantees a clean thread without an event loop.

---

## Plan

### Step 1: Fix `_run_job_safe` to actually call the scraper engine with a clean event loop

**File**: `apps/scraper/views.py` (function `_run_job_safe`, lines 431-471)

Currently this function is a stub with TODO comments. Replace it with:
- A fresh `asyncio.new_event_loop()` setup at the start to guarantee Playwright gets a clean loop
- An actual call to `run_scrape_job(job)` from `engine.py` (already imported)
- Proper error handling that sets job status to failed with the error message
- DB connection cleanup in `finally`

### Step 2: Apply the same event loop fix to `JobExecutor._execute_job_wrapper`

**File**: `apps/scraper/services/async_tasks.py` (method `_execute_job_wrapper`, line 90)

Add the same asyncio loop cleanup at the start of `_execute_job_wrapper` so that jobs submitted via the v2 API (`JobExecuteAPIView`) also get a clean event loop. Also add `connection.close()` in `finally` for DB connection cleanup.

---

## Summary of Files Changed

| File | Change |
|---|---|
| `apps/scraper/views.py` | Replace `_run_job_safe` stub with real engine call + asyncio loop fix |
| `apps/scraper/services/async_tasks.py` | Add asyncio loop fix + DB connection cleanup to `_execute_job_wrapper` |

---

## Why This Works

- `sync_playwright()` internally creates an asyncio event loop and runs Playwright's async API synchronously
- When called from a thread that already has an active event loop (inherited or leaked), it fails with the "async context" error
- By explicitly setting a fresh event loop at the start of each worker thread, we guarantee `sync_playwright()` can safely create and manage its own loop
- The `connection.close()` in `finally` ensures Django DB connections are properly cleaned up in worker threads (prevents connection leaks)
