"""Management command: sync TDM documents for qualified prospects.

Scrapes the document list from Miami-Dade RealTDM for every qualified prospect,
detects new documents, persists metadata to the DB, logs audit events, and
auto-downloads Surplus Claim/Affidavit, COM_SURPLUS, and SURPLUS_LETTER PDFs.

All run parameters are read from the JSON config file (default: apps/scraper/config/sync_config.json).
Edit that file to change filters, headless mode, dry-run, output_file, etc.

Usage:
    python manage.py sync_tdm_docs
    python manage.py sync_tdm_docs --config path/to/other_config.json
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
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



DOWNLOAD_TITLES = { "Surplus Claim/Affidavit",
    "SURPLUS LETTER",
    "SURPLUS_LETTER",
    "Title Search",}

BASE_DIR = Path(settings.BASE_DIR)
MEDIA_ROOT = Path(getattr(settings, "MEDIA_ROOT", BASE_DIR / "media"))
DEFAULT_CONFIG_PATH = BASE_DIR / "apps" / "scraper" / "config" / "sync_config.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "apps" / "scraper" / "config" / "tdm_sync_output.md"

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


def resolve_output_path(cfg, config_path):
    """Resolve the markdown output path from config or fall back to default."""
    raw = (cfg.get("output_file") or "").strip()
    if not raw:
        return DEFAULT_OUTPUT_PATH
    p = Path(raw)
    if not p.is_absolute():
        p = (Path(config_path).parent / p).resolve()
    return p



def safe_relative_path(path: Path) -> str:
    """Return a stable relative path; prefer MEDIA_ROOT-relative for DB storage."""
    p = Path(path).resolve()
    for root in (MEDIA_ROOT, BASE_DIR):
        try:
            return str(p.relative_to(Path(root).resolve()))
        except Exception:
            continue
    return str(p)

# ---------------------------------------------------------------------------
# Progress report helpers
# ---------------------------------------------------------------------------

def _fmt_dt(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        try:
            return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _append_event(progress, message):
    now_text = _fmt_dt(timezone.now())
    progress["events"].append(f"{now_text} — {message}")
    if len(progress["events"]) > 200:
        progress["events"] = progress["events"][-200:]


def _write_progress(output_path, progress):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    s = progress["stats"]
    lines = []

    lines.append("# TDM Document Sync Progress")
    lines.append("")

    # ── Run metadata ──────────────────────────────────────────────────────
    lines.append("## Run")
    lines.append(f"- Started: {_fmt_dt(progress['run_started'])}")
    lines.append(f"- Finished: {_fmt_dt(progress['run_finished']) if progress['run_finished'] else '-'}")
    lines.append(f"- Config: `{progress['config_path']}`")
    lines.append(f"- Output: `{progress['output_path']}`")
    lines.append(f"- Dry Run: `{progress['dry_run']}`")
    if progress["filters"]:
        lines.append(f"- Filters: `{', '.join(progress['filters'])}`")
    lines.append("")

    # ── Current ───────────────────────────────────────────────────────────
    lines.append("## Current")
    lines.append(f"- Processing: {progress['current'] or '-'}")
    lines.append("")

    # ── Stats ─────────────────────────────────────────────────────────────
    lines.append("## Stats")
    lines.append(f"- Total Prospects: `{progress['total_prospects']}`")
    lines.append(f"- Processed: `{s['processed']}`")
    lines.append(f"- New Docs Found: `{s['new_docs_found']}`")
    lines.append(f"- Docs Downloaded: `{s['docs_downloaded']}`")
    lines.append(f"- Download Errors: `{s['download_errors']}`")
    lines.append(f"- Scrape Errors: `{s['scrape_errors']}`")
    lines.append("")

    # ── Prospect rows ─────────────────────────────────────────────────────
    lines.append("## Prospects")
    lines.append(
        "| # | Case Number | County | State | Status | Scraped | New | Downloaded | DL Errors | Error |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---|")
    for row in progress["rows"]:
        scraped  = str(row["scraped"])  if row["scraped"]  is not None else "-"
        new_docs = str(row["new_docs"]) if row["new_docs"] is not None else "-"
        dl       = str(row["downloaded"])     if row["downloaded"]     is not None else "-"
        dl_err   = str(row["download_errors"]) if row["download_errors"] is not None else "-"
        error    = (row["error"] or "-").replace("|", "\\|").replace("\n", " ").strip()
        lines.append(
            f"| {row['index']} | {row['case_number']} | {row['county']} | {row['state']} "
            f"| {row['status']} | {scraped} | {new_docs} | {dl} | {dl_err} | {error} |"
        )
    lines.append("")

    # ── Event log ─────────────────────────────────────────────────────────
    lines.append("## Event Log")
    for event in progress["events"][-100:]:
        lines.append(f"- {event}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


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
# Download helper  — returns (downloaded_count, error_count)
# ---------------------------------------------------------------------------


def _looks_like_pdf(data: bytes) -> bool:
    if not data:
        return False
    return data.lstrip().startswith(b"%PDF-")


def _read_starts_with_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return _looks_like_pdf(fh.read(1024))
    except Exception:
        return False

def _resolve_local_file_path(local_path: str) -> Path | None:
    raw = (local_path or "").strip()
    if not raw:
        return None

    normalized = raw.replace("\\", "/")
    rel = Path(normalized)
    candidates = []

    raw_path = Path(raw)
    if raw_path.is_absolute():
        candidates.append(raw_path)

    candidates.append(MEDIA_ROOT / rel)
    candidates.append(BASE_DIR / rel)

    if normalized.startswith("media/"):
        candidates.append(MEDIA_ROOT / Path(normalized[len("media/"):]))

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _try_playwright_download(page, prospect, tdm_doc, dest: Path):
    """Fallback: capture a browser-managed download instead of request.get bytes."""
    try:
        with page.expect_download(timeout=12_000) as dl_info:
            if not find_and_click_view_button(page, prospect.case_number, tdm_doc.document_id):
                return False, "View button not found"
        download = dl_info.value
        download.save_as(str(dest))

        if _read_starts_with_pdf(dest):
            return True, ""

        try:
            dest.unlink()
        except Exception:
            pass
        return False, "Downloaded file is not a PDF"
    except PlaywrightTimeoutError:
        return False, "No browser download event"
    except Exception as exc:
        return False, str(exc)
def _download_pending(page, context, prospect, case_id, cfg):
    """Download any eligible docs not yet on disk. Returns (downloaded, errors)."""
    retry_failed = cfg.get("retry_failed", True)
    dry_run = cfg.get("dry_run", False)

    pending_filter = dict(
        prospect=prospect,
        is_auto_download=True,
        is_downloaded=False,
    )
    if not retry_failed:
        pending_filter["download_error"] = ""

    # Re-queue previously marked downloads if the stored file is missing or not a real PDF.
    if cfg.get("force_validate_downloaded", True) and not dry_run:
        downloaded_docs = ProspectTDMDocument.objects.filter(
            prospect=prospect,
            is_auto_download=True,
            is_downloaded=True,
        )
        for existing_doc in downloaded_docs:
            existing_path = _resolve_local_file_path(existing_doc.local_path)
            if existing_path is not None and _read_starts_with_pdf(existing_path):
                continue

            existing_doc.is_downloaded = False
            existing_doc.download_error = "Stored file missing or invalid PDF; re-queued"
            existing_doc.save(update_fields=["is_downloaded", "download_error", "last_checked_at"])

    pending = ProspectTDMDocument.objects.filter(**pending_filter)
    if not pending.exists():
        return 0, 0

    downloaded = 0
    errors = 0
    print(f"  [{prospect.case_number}] {pending.count()} pending download(s).")

    if dry_run:
        for tdm_doc in pending:
            print(f"  [{prospect.case_number}] [DRY RUN] Would download: {tdm_doc.title}")
        return 0, 0

    if not navigate_to_documents_tab(page, prospect.case_number, case_id):
        print(f"  [{prospect.case_number}] Could not navigate to Documents tab for downloads.")
        for tdm_doc in pending:
            tdm_doc.download_error = "Navigation to Documents tab failed"
            tdm_doc.save(update_fields=["download_error", "last_checked_at"])
            errors += 1
        return downloaded, errors

    dest_dir = MEDIA_ROOT / "prospects" / str(prospect.pk) / "tdm"
    dest_dir.mkdir(parents=True, exist_ok=True)

    pending_list = list(pending)
    for idx, tdm_doc in enumerate(pending_list):
        fname = safe_filename(tdm_doc.filename or tdm_doc.title)
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        dest = dest_dir / fname

        if dest.exists():
            if _read_starts_with_pdf(dest):
                tdm_doc.is_downloaded = True
                tdm_doc.downloaded_at = datetime.now()
                tdm_doc.local_path = safe_relative_path(dest)
                tdm_doc.download_error = ""
                tdm_doc.save(update_fields=["is_downloaded", "downloaded_at", "local_path", "download_error", "last_checked_at"])
                print(f"  [{prospect.case_number}] Already on disk: {fname}")
                downloaded += 1
                continue

            try:
                dest.unlink()
            except Exception:
                pass
            print(f"  [{prospect.case_number}] Existing file is not a PDF, re-downloading: {fname}")
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
                errors += 1
                continue

            api_resp = context.request.get(pdf_url, timeout=30_000)
            if api_resp.ok:
                body = api_resp.body()
                content_type = (api_resp.headers.get("content-type") or "").lower()

                if _looks_like_pdf(body):
                    dest.write_bytes(body)
                    tdm_doc.is_downloaded = True
                    tdm_doc.downloaded_at = datetime.now()
                    tdm_doc.local_path = safe_relative_path(dest)
                    tdm_doc.download_error = ""
                    tdm_doc.save(update_fields=["is_downloaded", "downloaded_at", "local_path", "download_error", "last_checked_at"])
                    print(f"  [{prospect.case_number}] Saved: {fname}")
                    downloaded += 1
                else:
                    fallback_ok, fallback_msg = _try_playwright_download(page, prospect, tdm_doc, dest)
                    if fallback_ok:
                        tdm_doc.is_downloaded = True
                        tdm_doc.downloaded_at = datetime.now()
                        tdm_doc.local_path = safe_relative_path(dest)
                        tdm_doc.download_error = ""
                        tdm_doc.save(update_fields=["is_downloaded", "downloaded_at", "local_path", "download_error", "last_checked_at"])
                        print(f"  [{prospect.case_number}] Saved via browser download: {fname}")
                        downloaded += 1
                    else:
                        tdm_doc.download_error = (
                            f"Non-PDF response ({content_type or 'unknown content-type'}); "
                            f"fallback failed: {fallback_msg}"
                        )
                        tdm_doc.save(update_fields=["download_error", "last_checked_at"])
                        print(
                            f"  [{prospect.case_number}] Non-PDF response for {fname}: "
                            f"{content_type or 'unknown content-type'}; fallback failed: {fallback_msg}"
                        )
                        errors += 1
            else:
                tdm_doc.download_error = f"HTTP {api_resp.status}"
                tdm_doc.save(update_fields=["download_error", "last_checked_at"])
                print(f"  [{prospect.case_number}] HTTP {api_resp.status} for {fname}")
                errors += 1
        except Exception as exc:
            tdm_doc.download_error = str(exc)
            tdm_doc.save(update_fields=["download_error", "last_checked_at"])
            print(f"  [{prospect.case_number}] Download error: {exc}")
            errors += 1

        time.sleep(1)

        # Re-navigate to Documents tab for the next document in the same case.
        # Clicking View can replace the current page or change the state.
        if idx < (len(pending_list) - 1):
            if not navigate_to_documents_tab(page, prospect.case_number, case_id):
                for remaining in pending_list[idx + 1:]:
                    remaining.download_error = "Navigation to Documents tab failed"
                    remaining.save(update_fields=["download_error", "last_checked_at"])
                    errors += 1
                break

    return downloaded, errors


# ---------------------------------------------------------------------------
# Per-prospect sync  — returns result dict for progress tracking
# ---------------------------------------------------------------------------

def sync_prospect(page, context, prospect, cfg):
    """Scrape, diff, persist, notify, and download. Returns a result dict."""
    dry_run = cfg.get("dry_run", False)
    tag = "[DRY RUN] " if dry_run else ""
    print(f"\n[{prospect.case_number}] {tag}Syncing TDM documents...")

    # 1. Scrape
    result = scrape_case_documents(page, prospect.case_number)
    if "error" in result:
        msg = result["error"]
        print(f"  [{prospect.case_number}] Scrape error: {msg}")
        return {"status": "scrape_error", "scraped": 0, "new_docs": 0,
                "downloaded": 0, "download_errors": 0, "error": msg}

    case_id = result.get("case_id", "")
    scraped_docs = result.get("documents", [])
    print(f"  [{prospect.case_number}] TDM returned {len(scraped_docs)} document(s).")

    # 2. Detect new documents
    existing_ids = set(
        ProspectTDMDocument.objects.filter(prospect=prospect)
        .values_list("document_id", flat=True)
    )
    new_docs = [
        d for d in scraped_docs
        if d.get("document_id") and d["document_id"] not in existing_ids
    ]

    # 3. Dry-run path
    if dry_run:
        if new_docs:
            for doc in new_docs:
                needs_dl = any(kw in doc.get("title", "") for kw in DOWNLOAD_TITLES)
                dl_flag = " [auto-download]" if needs_dl else ""
                print(f"  [{prospect.case_number}] [DRY RUN] Would create: {doc.get('title', '?')}{dl_flag}")
        else:
            print(f"  [{prospect.case_number}] No new documents.")
        dl, dl_err = _download_pending(page, context, prospect, case_id, cfg)
        return {"status": "dry-run", "scraped": len(scraped_docs), "new_docs": len(new_docs),
                "downloaded": dl, "download_errors": dl_err, "error": ""}

    # 4. Persist new documents
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

    # 5. Log and note if new docs found
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

    # 6. Download
    dl, dl_err = _download_pending(page, context, prospect, case_id, cfg)

    return {
        "status": "completed",
        "scraped": len(scraped_docs),
        "new_docs": len(new_docs),
        "downloaded": dl,
        "download_errors": dl_err,
        "error": "",
    }


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
        config_path = options["config"]
        cfg = build_config(options)
        output_path = resolve_output_path(cfg, config_path)

        dry_run = cfg.get("dry_run", False)
        headless = cfg.get("headless", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE — no DB writes or file saves ==="))

        # Active filter summary
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

        # Initialise progress
        progress = {
            "run_started": timezone.now(),
            "run_finished": None,
            "config_path": str(config_path),
            "output_path": str(output_path),
            "dry_run": dry_run,
            "filters": filters,
            "total_prospects": len(prospects),
            "current": "",
            "stats": {
                "processed": 0,
                "new_docs_found": 0,
                "docs_downloaded": 0,
                "download_errors": 0,
                "scrape_errors": 0,
            },
            "rows": [],
            "events": [],
        }
        _append_event(progress, f"Started sync for {len(prospects)} prospect(s).")
        _write_progress(output_path, progress)

        if not prospects:
            progress["run_finished"] = timezone.now()
            _append_event(progress, "Nothing to do.")
            _write_progress(output_path, progress)
            self.stdout.write("Nothing to do.")
            return

        self.stdout.write(f"Progress report: {output_path}")

        # sync_playwright() creates an asyncio event loop internally; Django's
        # ORM async_unsafe guard mistakenly thinks we're in an async context.
        # Setting this env var tells Django to allow synchronous ORM calls here.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(**BROWSER_ARGS)
            page = context.new_page()

            for index, prospect in enumerate(prospects, start=1):
                label = f"[{index}/{len(prospects)}] {prospect.case_number}"
                progress["current"] = label
                _append_event(progress, f"Processing {prospect.case_number} ({prospect.county})")

                row = {
                    "index": index,
                    "case_number": prospect.case_number,
                    "county": prospect.county.name,
                    "state": prospect.county.state.abbreviation,
                    "status": "running",
                    "scraped": None,
                    "new_docs": None,
                    "downloaded": None,
                    "download_errors": None,
                    "error": "",
                }
                progress["rows"].append(row)
                _write_progress(output_path, progress)

                try:
                    res = sync_prospect(page, context, prospect, cfg)

                    row["status"]         = res["status"]
                    row["scraped"]        = res["scraped"]
                    row["new_docs"]       = res["new_docs"]
                    row["downloaded"]     = res["downloaded"]
                    row["download_errors"] = res["download_errors"]
                    row["error"]          = res.get("error", "")

                    s = progress["stats"]
                    s["processed"]       += 1
                    s["new_docs_found"]  += res["new_docs"]
                    s["docs_downloaded"] += res["downloaded"]
                    s["download_errors"] += res["download_errors"]
                    if res["status"] == "scrape_error":
                        s["scrape_errors"] += 1

                    _append_event(
                        progress,
                        f"[{prospect.case_number}] scraped={res['scraped']} new={res['new_docs']} "
                        f"downloaded={res['downloaded']} dl_errors={res['download_errors']}"
                    )

                except Exception as exc:
                    row["status"] = "error"
                    row["error"]  = str(exc)
                    progress["stats"]["scrape_errors"] += 1
                    _append_event(progress, f"[{prospect.case_number}] Unhandled error: {exc}")
                    self.stderr.write(self.style.ERROR(f"[{prospect.case_number}] Unhandled error: {exc}"))

                _write_progress(output_path, progress)

            context.close()
            browser.close()

        progress["current"] = ""
        progress["run_finished"] = timezone.now()
        s = progress["stats"]
        _append_event(
            progress,
            f"Sync complete. processed={s['processed']} new_docs={s['new_docs_found']} "
            f"downloaded={s['docs_downloaded']} dl_errors={s['download_errors']} "
            f"scrape_errors={s['scrape_errors']}"
        )
        _write_progress(output_path, progress)

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete. processed={s['processed']} new_docs={s['new_docs_found']} "
            f"downloaded={s['docs_downloaded']} dl_errors={s['download_errors']} "
            f"scrape_errors={s['scrape_errors']}"
        ))


















