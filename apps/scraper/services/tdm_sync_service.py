"""Background TDM sync service for single-prospect on-demand scraping.

Reuses sync_prospect() and BROWSER_ARGS from the sync_tdm_docs management command.
Status is tracked in-process via a thread-safe dict keyed by prospect PK.
"""
import os
import threading
from datetime import datetime


_lock = threading.Lock()
_status: dict[int, dict] = {}  # prospect_pk -> status dict

DEFAULT_CFG = {
    "dry_run": False,
    "headless": True,
    "retry_failed": True,
    "force_validate_downloaded": True,
}


def get_sync_status(prospect_pk: int) -> dict:
    """Return a copy of the current sync status for this prospect."""
    with _lock:
        return dict(_status.get(prospect_pk, {"state": "idle"}))


def start_tdm_sync(prospect_pk: int, cfg: dict | None = None) -> bool:
    """Start a background TDM sync for one prospect.

    Returns False if a sync is already running for this prospect, True otherwise.
    """
    with _lock:
        if _status.get(prospect_pk, {}).get("state") == "running":
            return False
        _status[prospect_pk] = {
            "state": "running",
            "started_at": datetime.now().isoformat(),
        }
    thread = threading.Thread(
        target=_run_sync,
        args=(prospect_pk, cfg or DEFAULT_CFG),
        daemon=True,
    )
    thread.start()
    return True


def _run_sync(prospect_pk: int, cfg: dict) -> None:
    """Thread target: run Playwright, call sync_prospect(), store result."""
    # sync_playwright() creates an asyncio event loop internally; this env var
    # prevents Django's async_unsafe guard from raising inside the thread.
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    try:
        from playwright.sync_api import sync_playwright
        from apps.prospects.models import Prospect
        from apps.scraper.management.commands.sync_tdm_docs import (
            sync_prospect,
            BROWSER_ARGS,
        )

        prospect = Prospect.objects.select_related(
            "county", "county__state"
        ).get(pk=prospect_pk)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=cfg.get("headless", True))
            context = browser.new_context(**BROWSER_ARGS)
            page = context.new_page()
            try:
                result = sync_prospect(page, context, prospect, cfg)
            finally:
                context.close()
                browser.close()

        with _lock:
            _status[prospect_pk] = {
                "state": "completed",
                "result": result,
                "finished_at": datetime.now().isoformat(),
            }
    except Exception as exc:
        with _lock:
            _status[prospect_pk] = {
                "state": "failed",
                "error": str(exc),
                "finished_at": datetime.now().isoformat(),
            }
