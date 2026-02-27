# -*- coding: utf-8 -*-
"""Download Surplus Claim/Affidavit PDFs from TDM by clicking the View button.

Reads tdm_documents.json, navigates to each case's Documents tab via Playwright,
finds the View button by data-documentid, clicks it, and saves the downloaded file.

Usage:
    python download_surplus_affidavit_headless.py
    python download_surplus_affidavit_headless.py --input results.json --output-dir pdfs
    python download_surplus_affidavit_headless.py --headed
"""

import argparse
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://miamidade.realtdm.com/public/cases/List"
MATCH_KEYWORD = "Surplus Claim/Affidavit"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Surplus Claim/Affidavit PDFs from TDM."
    )
    parser.add_argument(
        "--input",
        default="tdm_documents.json",
        help="JSON file from scrape_tdm_docs.py (default: tdm_documents.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="Folder to save PDFs (default: downloads/)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=False,
        help="Run browser with a visible window (default: headless)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def collect_targets(data: list) -> list[dict]:
    """Return all Surplus Claim/Affidavit docs that have a document_id."""
    targets = []
    for case in data:
        case_number = case.get("case_number", "unknown")
        case_id = case.get("case_id", "")
        if not case_id:
            print(f"[{case_number}] WARNING --- no case_id in JSON; re-run scraper first")
            continue
        for doc in case.get("documents", []):
            if MATCH_KEYWORD in doc.get("title", ""):
                doc_id = doc.get("document_id", "")
                if not doc_id:
                    print(f"[{case_number}] WARNING --- '{doc['title']}' has no document_id; re-run scraper first")
                    continue
                targets.append({
                    "case_number": case_number,
                    "case_id": case_id,
                    "title": doc["title"],
                    "filename": doc.get("filename", ""),
                    "document_id": doc_id,
                    "doc_type": doc.get("doc_type", ""),
                })
    return targets


def navigate_to_documents_tab(page, case_number: str, case_id: str) -> bool:
    """Navigate to the Documents tab using the same proven flow as the scraper:
    list page --- search --- checkbox --- batchActions --- Documents tab.
    """
    # 1. Navigate to list page
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        print(f"[{case_number}] ERROR --- navigation failed: {exc}")
        return False

    time.sleep(1)

    # 2. Type case number into search input
    try:
        search_input = page.locator("input[name*='filterCaseNumber']").first
        search_input.wait_for(state="visible", timeout=5_000)
        search_input.fill("")
        search_input.type(case_number, delay=50)
    except Exception as exc:
        print(f"[{case_number}] ERROR --- search input: {exc}")
        return False

    # 3. Click Search button
    try:
        search_btn = page.locator("button:has-text('Search')").first
        search_btn.wait_for(state="visible", timeout=5_000)
        # JS click avoids overlay intercepts that block pointer events in headless
        search_btn.evaluate("el => el.click()")
    except Exception as exc:
        print(f"[{case_number}] ERROR --- search button: {exc}")
        return False

    time.sleep(2)

    # 4a. Wait for results table
    try:
        page.wait_for_selector("table#county-setup", timeout=10_000)
    except Exception as exc:
        print(f"[{case_number}] ERROR --- results table: {exc}")
        return False

    # 4b. Check selectedCases checkbox (hidden --- JS click)
    try:
        checkbox = page.locator(
            "table#county-setup tbody tr:first-child input[name='selectedCases']"
        ).first
        checkbox.wait_for(state="attached", timeout=5_000)
        checkbox.evaluate("el => el.click()")
    except Exception as exc:
        print(f"[{case_number}] ERROR --- checkbox: {exc}")
        return False

    time.sleep(1)

    # 4c. Click Batch Actions
    try:
        batch_btn = page.locator("#batchActions").first
        batch_btn.wait_for(state="visible", timeout=5_000)
        batch_btn.click()
        print(f"[{case_number}] Clicked batchActions")
    except Exception as exc:
        print(f"[{case_number}] ERROR --- batchActions: {exc}")
        return False

    time.sleep(2)

    # 5. Wait for case detail tab strip
    try:
        page.wait_for_selector("div.public-tabs", state="attached", timeout=15_000)
        print(f"[{case_number}] Case detail loaded")
    except Exception as exc:
        print(f"[{case_number}] ERROR --- case detail page did not load: {exc}")
        return False

    time.sleep(1)

    # 6. Click Documents tab (JS click --- href is javascript:void(0))
    try:
        doc_tab = page.locator("a.public-tab[data-handler='dspCaseDocuments']").first
        doc_tab.wait_for(state="attached", timeout=10_000)
        doc_tab.evaluate("el => el.click()")
        print(f"[{case_number}] Clicked Documents tab")
    except Exception as exc:
        print(f"[{case_number}] ERROR --- Documents tab: {exc}")
        return False

    time.sleep(2)

    # 7. Wait for documents table
    try:
        page.wait_for_selector("table.table-public", timeout=10_000)
    except Exception as exc:
        print(f"[{case_number}] ERROR --- documents table: {exc}")
        return False

    time.sleep(1)
    return True


def find_and_click_view_button(page, case_number: str, document_id: str) -> bool:
    """Locate the View button by data-documentid across all pages and click it.
    Returns True if the button was found and clicked.
    """
    page_num = 1

    while True:
        # Try to find the button on the current page
        btn_selector = f"button.btn[data-documentid='{document_id}']"
        btn = page.locator(btn_selector).first
        try:
            btn.wait_for(state="attached", timeout=3_000)
            btn.click()
            print(f"[{case_number}] Clicked View button for document_id={document_id} on page {page_num}")
            return True
        except Exception:
            pass

        # Not found --- try next pagination page
        try:
            next_page_num = page_num + 1
            next_link = page.locator(
                f"a.public-pagination-page[data-pagenumber='{next_page_num}']"
            ).first
            next_link.wait_for(state="attached", timeout=3_000)
            next_link.evaluate("el => el.click()")
            page_num = next_page_num
            time.sleep(2)
            page.wait_for_selector("table.table-public", timeout=8_000)
            time.sleep(1)
        except Exception:
            print(f"[{case_number}] ERROR --- View button for document_id={document_id} not found")
            return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        return

    data = json.loads(input_path.read_text(encoding="utf-8"))
    targets = collect_targets(data)

    if not targets:
        print(f"No '{MATCH_KEYWORD}' documents with a document_id found in {input_path}.")
        print("Tip: re-run scrape_tdm_docs.py to refresh the JSON.")
        return

    print(f"Found {len(targets)} document(s) to download:")
    for t in targets:
        print(f"  [{t['case_number']}] {t['title']} | {t['filename']} (id={t['document_id']})")

    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Group targets by case_number to avoid re-navigating for each doc
        from itertools import groupby
        targets.sort(key=lambda x: x["case_number"])

        for case_number, docs_iter in groupby(targets, key=lambda x: x["case_number"]):
            docs = list(docs_iter)
            case_dir = output_dir / case_number
            case_dir.mkdir(parents=True, exist_ok=True)

            case_id = docs[0]["case_id"]
            print(f"\n[{case_number}] Loading case {case_id} via caseDetails()...")
            if not navigate_to_documents_tab(page, case_number, case_id):
                print(f"[{case_number}] Skipping all documents for this case")
                continue

            for target in docs:
                # Build destination filename from the stored filename field
                fname = safe_filename(target["filename"] or target["title"])
                if not fname.lower().endswith(".pdf"):
                    fname += ".pdf"
                dest = case_dir / fname

                if dest.exists():
                    print(f"[{case_number}] Already exists, skipping: {fname}")
                    continue

                print(f"[{case_number}] Downloading: {fname} (document_id={target['document_id']})")

                try:
                    # View button usually opens PDF in a new tab, but headless can load it in the same tab.
                    pdf_url = None

                    try:
                        with context.expect_page(timeout=10_000) as new_page_info:
                            if not find_and_click_view_button(page, case_number, target["document_id"]):
                                continue
                        pdf_tab = new_page_info.value
                        pdf_tab.wait_for_load_state("domcontentloaded", timeout=30_000)
                        pdf_url = pdf_tab.url
                        print(f"[{case_number}] PDF tab URL: {pdf_url}")
                        pdf_tab.close()
                    except PlaywrightTimeoutError:
                        # Fallback: wait for a PDF response in the same tab
                        def is_pdf_response(resp):
                            try:
                                ct = (resp.headers.get("content-type") or "").lower()
                            except Exception:
                                ct = ""
                            return ("pdf" in ct) or resp.url.lower().endswith(".pdf")

                        try:
                            with page.expect_response(is_pdf_response, timeout=15_000) as resp_info:
                                if not find_and_click_view_button(page, case_number, target["document_id"]):
                                    continue
                            resp = resp_info.value
                            pdf_url = resp.url
                            print(f"[{case_number}] PDF response URL: {pdf_url}")
                        except PlaywrightTimeoutError:
                            # Last chance: check if the current tab navigated to a PDF URL
                            if page.url and page.url != BASE_URL:
                                pdf_url = page.url
                                print(f"[{case_number}] PDF current URL: {pdf_url}")

                    if not pdf_url:
                        print(f"[{case_number}] ERROR - no PDF URL found for document_id={target['document_id']}")
                        continue

                    # Download PDF bytes using the browser session (shares cookies)
                    api_resp = context.request.get(pdf_url, timeout=30_000)
                    if api_resp.ok:
                        dest.write_bytes(api_resp.body())
                        print(f"[{case_number}] Saved: {dest}")
                    else:
                        print(f"[{case_number}] ERROR - HTTP {api_resp.status} for {pdf_url}")

                except Exception as exc:
                    print(f"[{case_number}] ERROR - {exc}")


                time.sleep(1)

                # Re-navigate to Documents tab for next document in same case
                # (clicking View may have changed the page state)
                if docs.index(target) < len(docs) - 1:
                    print(f"[{case_number}] Re-navigating for next document...")
                    navigate_to_documents_tab(page, case_number, case_id)

        context.close()
        browser.close()

    print(f"\nDone. Files saved under: {output_dir.resolve()}")


if __name__ == "__main__":
    main()





