"""Management command: sync TDM documents for qualified prospects.

Scrapes the document list from Miami-Dade RealTDM for every qualified prospect,
detects new documents, persists metadata to the DB, logs audit events, and
auto-downloads Surplus Claim/Affidavit, COM_SURPLUS, and SURPLUS_LETTER PDFs.

All run parameters are read from the JSON config file (default: apps/scraper/config/sync_config.json).
Edit that file to change filters, headless mode, dry-run, etc.

Usage:
    python manage.py sync_tdm_docs
    python manage.py sync_tdm_docs --config path/to/other_config.json
"""

import json
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from apps.prospects.models import (
    Prospect,
    ProspectNote,
    ProspectTDMDocument,
    log_prospect_action,
)
from tdm.scrape_tdm_docs import scrape_case_documents
from tdm.download_surplus_affidavit_headless import (
    find_and_click_view_button,
    navigate_to_documents_tab,
    safe_filename,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOWNLOAD_TITLES = {"Surplus Claim/Affidavit", "COM_SURPLUS", "SURPLUS_LETTER"}

BASE_DIR = Path(settings.BASE_DIR)
MEDIA_ROOT = Path(getattr(settings, "MEDIA_ROOT", BASE_DIR / "media"))
DEFAULT_CONFIG_PATH = BASE_DIR / "apps" / "scraper" / "config" / "sync_config.json"

BROWSER_ARGS = dict(
    viewport={"width": 1280, "height": 900},
    accept_downloads=True,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path):
    """Load JSON config file; return empty dict if file is missing or unreadable."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Warning: could not load config file {path}: {exc}")
        return {}


def build_config(options):
    """Load config from the JSON file specified by --config."""
    return load_config(options["config"])


# ---------------------------------------------------------------------------
# Prospect filtering
# ---------------------------------------------------------------------------

def get_qualified_prospects(cfg):
    """Return a queryset of qualified prospects filtered by *cfg*."""
    qs = (
        Prospect.objects.filter(qualification_status="qualified")
        .exclude(case_number="")
        .select_related("county", "county__state")
    )

    case_numbers = cfg.get("case_numbers") or []
    if case_numbers:
        qs = qs.filter(case_number__in=case_numbers)

    state = (cfg.get("state") or "").strip().upper()
    if state:
        qs = qs.filter(county__state__abbreviation=state)

    prospect_type = (cfg.get("prospect_type") or "").strip().upper()
    if prospect_type:
        qs = qs.filter(prospect_type=prospect_type)

    counties = cfg.get("counties") or []
    if counties:
        qs = qs.filter(county__name__in=counties)

    auction_start = (cfg.get("auction_start_date") or "").strip()
    if auction_start:
        try:
            start_date = datetime.strptime(auction_start, "%Y-%m-%d").date()
            qs = qs.filter(auction_date__gte=start_date)
        except ValueError:
            print(f"Warning: invalid auction_start_date '{auction_start}' (expected YYYY-MM-DD), ignoring.")

    auction_end = (cfg.get("auction_end_date") or "").strip()
    if auction_end:
        try:
            end_date = datetime.strptime(auction_end, "%Y-%m-%d").date()
            qs = qs.filter(auction_date__lte=end_date)
        except ValueError:
            print(f"Warning: invalid auction_end_date '{auction_end}' (expected YYYY-MM-DD), ignoring.")

    if cfg.get("skip_completed"):
        qs = qs.filter(
            tdm_documents__is_auto_download=True,
            tdm_documents__is_downloaded=False,
        ).distinct()

    return qs


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _download_pending(page, context, prospect, case_id, cfg):
    """Download any eligible docs not yet on disk for *prospect*."""
    retry_failed = cfg.get("retry_failed", True)
    dry_run = cfg.get("dry_run", False)

    pending_filter = dict(
        prospect=prospect,
        is_auto_download=True,
        is_downloaded=False,
    )
    if not retry_failed:
        pending_filter["download_error"] = ""

    pending = ProspectTDMDocument.objects.filter(**pending_filter)
    if not pending.exists():
        return

    print(f"  [{prospect.case_number}] {pending.count()} pending download(s).")

    if dry_run:
        for tdm_doc in pending:
            print(f"  [{prospect.case_number}] [DRY RUN] Would download: {tdm_doc.title}")
        return

    if not navigate_to_documents_tab(page, prospect.case_number, case_id):
        print(f"  [{prospect.case_number}] Could not navigate to Documents tab for downloads.")
        for tdm_doc in pending:
            tdm_doc.download_error = "Navigation to Documents tab failed"
            tdm_doc.save(update_fields=["download_error", "last_checked_at"])
        return

    dest_dir = MEDIA_ROOT / "prospects" / str(prospect.pk) / "tdm"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for tdm_doc in pending:
        fname = safe_filename(tdm_doc.filename or tdm_doc.title)
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        dest = dest_dir / fname

        if dest.exists():
            tdm_doc.is_downloaded = True
            tdm_doc.downloaded_at = datetime.now()
            tdm_doc.local_path = str(dest.relative_to(BASE_DIR))
            tdm_doc.download_error = ""
            tdm_doc.save(update_fields=["is_downloaded", "downloaded_at", "local_path", "download_error", "last_checked_at"])
            print(f"  [{prospect.case_number}] Already on disk: {fname}")
            continue

        try:
            pdf_url = None

            # Strategy 1: new tab
            try:
                with context.expect_page(timeout=10_000) as new_page_info:
                    if not find_and_click_view_button(page, prospect.case_number, tdm_doc.document_id):
                        continue
                pdf_tab = new_page_info.value
                pdf_tab.wait_for_load_state("domcontentloaded", timeout=30_000)
                pdf_url = pdf_tab.url
                pdf_tab.close()
            except PlaywrightTimeoutError:
                # Strategy 2: PDF response in same tab
                try:
                    def is_pdf_response(resp):
                        try:
                            ct = (resp.headers.get("content-type") or "").lower()
                        except Exception:
                            ct = ""
                        return "pdf" in ct or resp.url.lower().endswith(".pdf")

                    with page.expect_response(is_pdf_response, timeout=15_000) as resp_info:
                        if not find_and_click_view_button(page, prospect.case_number, tdm_doc.document_id):
                            continue
                    pdf_url = resp_info.value.url
                except PlaywrightTimeoutError:
                    # Strategy 3: current page URL
                    if page.url and page.url != "https://miamidade.realtdm.com/public/cases/List":
                        pdf_url = page.url

            if not pdf_url:
                tdm_doc.download_error = "No PDF URL captured"
                tdm_doc.save(update_fields=["download_error", "last_checked_at"])
                print(f"  [{prospect.case_number}] No PDF URL for document_id={tdm_doc.document_id}")
                continue

            api_resp = context.request.get(pdf_url, timeout=30_000)
            if api_resp.ok:
                dest.write_bytes(api_resp.body())
                tdm_doc.is_downloaded = True
                tdm_doc.downloaded_at = datetime.now()
                tdm_doc.local_path = str(dest.relative_to(BASE_DIR))
                tdm_doc.download_error = ""
                tdm_doc.save(update_fields=["is_downloaded", "downloaded_at", "local_path", "download_error", "last_checked_at"])
                print(f"  [{prospect.case_number}] Saved: {fname}")
            else:
                tdm_doc.download_error = f"HTTP {api_resp.status}"
                tdm_doc.save(update_fields=["download_error", "last_checked_at"])
                print(f"  [{prospect.case_number}] HTTP {api_resp.status} for {fname}")

        except Exception as exc:
            tdm_doc.download_error = str(exc)
            tdm_doc.save(update_fields=["download_error", "last_checked_at"])
            print(f"  [{prospect.case_number}] Download error: {exc}")

        time.sleep(1)


# ---------------------------------------------------------------------------
# Per-prospect sync
# ---------------------------------------------------------------------------

def sync_prospect(page, context, prospect, cfg):
    """Scrape, diff, persist, notify, and download for a single prospect."""
    dry_run = cfg.get("dry_run", False)
    tag = "[DRY RUN] " if dry_run else ""
    print(f"\n[{prospect.case_number}] {tag}Syncing TDM documents...")

    result = scrape_case_documents(page, prospect.case_number)
    if "error" in result:
        print(f"  [{prospect.case_number}] Scrape error: {result['error']}")
        return

    case_id = result.get("case_id", "")
    scraped_docs = result.get("documents", [])
    print(f"  [{prospect.case_number}] TDM returned {len(scraped_docs)} document(s).")

    existing_ids = set(
        ProspectTDMDocument.objects.filter(prospect=prospect)
        .values_list("document_id", flat=True)
    )
    new_docs = [
        d for d in scraped_docs
        if d.get("document_id") and d["document_id"] not in existing_ids
    ]

    if dry_run:
        if new_docs:
            for doc in new_docs:
                needs_dl = any(kw in doc.get("title", "") for kw in DOWNLOAD_TITLES)
                dl_flag = " [auto-download]" if needs_dl else ""
                print(f"  [{prospect.case_number}] [DRY RUN] Would create: {doc.get('title', '?')}{dl_flag}")
        else:
            print(f"  [{prospect.case_number}] No new documents.")
        _download_pending(page, context, prospect, case_id, cfg)
        return

    for doc in new_docs:
        needs_download = any(kw in doc.get("title", "") for kw in DOWNLOAD_TITLES)
        ProspectTDMDocument.objects.create(
            prospect=prospect,
            case_id=case_id,
            document_id=doc["document_id"],
            title=doc.get("title", ""),
            filename=doc.get("filename", ""),
            details=doc.get("details", ""),
            doc_date=doc.get("date", ""),
            doc_type=doc.get("doc_type", ""),
            is_auto_download=needs_download,
        )

    if new_docs:
        titles_str = ", ".join(d.get("title", "") for d in new_docs)
        desc = f"TDM sync: {len(new_docs)} new document(s) found \u2014 {titles_str}"
        log_prospect_action(
            prospect=prospect,
            user=None,
            action_type="updated",
            description=desc,
            metadata={
                "new_document_count": len(new_docs),
                "document_titles": [d.get("title", "") for d in new_docs],
            },
        )
        ProspectNote.objects.create(
            prospect=prospect,
            author=None,
            content=f"[TDM Auto-Sync] {desc}",
        )
        print(f"  [{prospect.case_number}] {len(new_docs)} new document(s) logged and noted.")
    else:
        print(f"  [{prospect.case_number}] No new documents.")

    _download_pending(page, context, prospect, case_id, cfg)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Sync TDM documents for all qualified prospects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            default=str(DEFAULT_CONFIG_PATH),
            metavar="PATH",
            help="Path to JSON config file (default: apps/scraper/config/sync_config.json)",
        )

    def handle(self, *args, **options):
        cfg = build_config(options)

        dry_run = cfg.get("dry_run", False)
        headless = cfg.get("headless", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE — no DB writes or file saves ==="))

        # Summarise active filters
        filters = []
        if cfg.get("state"):              filters.append(f"state={cfg['state']}")
        if cfg.get("prospect_type"):      filters.append(f"type={cfg['prospect_type']}")
        if cfg.get("counties"):           filters.append(f"counties={cfg['counties']}")
        if cfg.get("auction_start_date"): filters.append(f"auction>={cfg['auction_start_date']}")
        if cfg.get("auction_end_date"):   filters.append(f"auction<={cfg['auction_end_date']}")
        if cfg.get("case_numbers"):       filters.append(f"case_numbers={cfg['case_numbers']}")
        if cfg.get("skip_completed"):     filters.append("skip_completed=True")
        if not cfg.get("retry_failed", True): filters.append("retry_failed=False")
        if filters:
            self.stdout.write(f"Active filters: {', '.join(filters)}")

        prospects = list(get_qualified_prospects(cfg))
        self.stdout.write(f"Found {len(prospects)} qualified prospect(s) to sync.")

        if not prospects:
            self.stdout.write("Nothing to do.")
            return

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(**BROWSER_ARGS)
            page = context.new_page()

            for prospect in prospects:
                try:
                    sync_prospect(page, context, prospect, cfg)
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"[{prospect.case_number}] Unhandled error: {exc}"))

            context.close()
            browser.close()

        self.stdout.write(self.style.SUCCESS("\nSync complete."))
