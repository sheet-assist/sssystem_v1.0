"""Standalone scraper for TDM case documents.

Usage:
    python scrape_tdm_docs.py --cases 2025A00447,2025B00123
    python scrape_tdm_docs.py --file cases.txt
    python scrape_tdm_docs.py --cases 2025A00447 --output results.json --headless
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://miamidade.realtdm.com/public/cases/List"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape document metadata from Miami-Dade TDM case pages."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--cases",
        help="Comma-separated case numbers, e.g. 2025A00447,2025B00123",
    )
    group.add_argument(
        "--file",
        help="Path to a text file with one case number per line",
    )
    parser.add_argument(
        "--output",
        default="tdm_documents.json",
        help="Output JSON file path (default: tdm_documents.json)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: visible)",
    )
    return parser.parse_args()


def load_case_numbers(args) -> list[str]:
    if args.cases:
        return [c.strip() for c in args.cases.split(",") if c.strip()]
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)
    lines = file_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def _extract_documents(html: str) -> list[dict]:
    """Parse document rows from table.table-public using BeautifulSoup.

    Table columns (from live HTML):
        col 0 — icon (skip)
        col 1 — <strong>Document type</strong>
                 <div class="text-small muted">filename.pdf</div>
        col 2 — Details
        col 3 — Upload Date
        col 4 — <button data-documentid="..." data-doctype="...">View</button>
    """
    soup = BeautifulSoup(html, "html.parser")
    documents = []

    rows = soup.select("table.table-public tbody tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        # col 1 — document type (<strong>) and filename (.text-small.muted)
        title_cell = cells[1]
        strong = title_cell.find("strong")
        title = strong.get_text(strip=True) if strong else title_cell.get_text(" ", strip=True)
        if not title:
            continue

        muted = title_cell.find("div", class_=lambda c: c and "muted" in c)
        filename = muted.get_text(strip=True) if muted else ""

        # col 2 — details
        details = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""

        # col 3 — upload date
        date = cells[3].get_text(strip=True) if len(cells) > 3 else ""

        # col 4 — View button; capture document_id and doc_type (no URL)
        document_id = ""
        doc_type = ""
        if len(cells) > 4:
            btn = cells[4].find("button", attrs={"data-documentid": True})
            if btn:
                document_id = btn.get("data-documentid", "")
                doc_type = btn.get("data-doctype", "")

        documents.append({
            "title": title,
            "filename": filename,
            "details": details,
            "date": date,
            "document_id": document_id,
            "doc_type": doc_type,
        })

    return documents


def scrape_case_documents(page, case_number: str) -> dict:
    """Navigate TDM, search for *case_number*, scrape the Documents tab.

    Returns a dict with keys: case_number, scraped_at, documents (and
    optionally error).
    """
    result: dict = {
        "case_number": case_number,
        "case_id": "",          # populated from data-caseid once results load
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "documents": [],
    }

    print(f"\n[{case_number}] Navigating to {BASE_URL}")

    # ------------------------------------------------------------------
    # 1. Navigate to the list page
    # ------------------------------------------------------------------
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError as exc:
        result["error"] = f"Navigation timeout: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result
    except Exception as exc:
        result["error"] = f"Navigation failed: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    time.sleep(1)

    # ------------------------------------------------------------------
    # 2. Type the case number into the search input
    # ------------------------------------------------------------------
    search_selectors = [
        # "input[placeholder*='Case']",
        # "input[placeholder*='case']",
        "input[name*='filterCaseNumber']",
        # "input[name*='Case']",
        # "input[id*='case']",
        # "input[id*='Case']",
        # "input[id*='search']",
        # "input[type='text']",
    ]
    search_input = None
    for sel in search_selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=5_000)
            search_input = locator
            print(f"[{case_number}] Found search input via selector: {sel}")
            break
        except Exception:
            continue

    if search_input is None:
        result["error"] = "Could not locate the search input field"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    try:
        search_input.fill("")
        search_input.type(case_number, delay=50)
    except Exception as exc:
        result["error"] = f"Could not type case number: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    # ------------------------------------------------------------------
    # 3. Click the Search button
    # ------------------------------------------------------------------
    search_btn_selectors = [
        "button:has-text('Search')",
        "input[type='submit'][value*='Search']",
        "input[type='button'][value*='Search']",
        "a:has-text('Search')",
        "button[type='submit']",
    ]
    search_btn = None
    for sel in search_btn_selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=3_000)
            search_btn = locator
            print(f"[{case_number}] Found search button via selector: {sel}")
            break
        except Exception:
            continue

    if search_btn is None:
        # Fall back to pressing Enter in the search field
        print(f"[{case_number}] Search button not found – pressing Enter instead")
        try:
            search_input.press("Enter")
        except Exception as exc:
            result["error"] = f"Could not submit search: {exc}"
            print(f"[{case_number}] ERROR – {result['error']}")
            return result
    else:
        try:
            # JS click avoids overlay intercepts that can block pointer events in headless
            search_btn.evaluate("el => el.click()")
        except Exception as exc:
            result["error"] = f"Could not click search button: {exc}"
            print(f"[{case_number}] ERROR – {result['error']}")
            return result

    time.sleep(2)

    # ------------------------------------------------------------------
    # 4. Select first row in results table and open batch actions
    # ------------------------------------------------------------------

    # 4a. Wait for the results table (#county-setup) to appear
    try:
        page.wait_for_selector("table#county-setup", timeout=10_000)
        print(f"[{case_number}] Results table #county-setup found")
    except Exception:
        page_text = page.content().lower()
        if "no results" in page_text or "no records" in page_text or "not found" in page_text:
            result["error"] = "No results found"
        else:
            result["error"] = "Results table #county-setup did not appear"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    # 4b. Click the checkbox in the first data row (hidden input — use JS click)
    #     Also grab data-caseid so downstream scripts can load the case directly.
    try:
        checkbox = page.locator(
            "table#county-setup tbody tr:first-child input[name='selectedCases']"
        ).first
        checkbox.wait_for(state="attached", timeout=5_000)
        case_id = checkbox.get_attribute("data-caseid") or ""
        if case_id:
            result["case_id"] = case_id
            print(f"[{case_number}] case_id={case_id}")
        checkbox.evaluate("el => el.click()")
        print(f"[{case_number}] Checked selectedCases checkbox on first row")
    except Exception as exc:
        result["error"] = f"Could not click #selectedCases checkbox: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    time.sleep(1)

    # 4c. Click the Batch Actions button
    try:
        batch_btn = page.locator("#batchActions").first
        batch_btn.wait_for(state="visible", timeout=5_000)
        batch_btn.click()
        print(f"[{case_number}] Clicked #batchActions button")
    except Exception as exc:
        result["error"] = f"Could not click #batchActions button: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    time.sleep(2)

    # ------------------------------------------------------------------
    # 5. Wait for the case detail tab strip to load
    # ------------------------------------------------------------------
    try:
        page.wait_for_selector("div.public-tabs", state="attached", timeout=15_000)
        print(f"[{case_number}] Case detail tab strip (div.public-tabs) loaded")
    except Exception as exc:
        result["error"] = f"Case detail page did not load: {exc}"
        print(f"[{case_number}] ERROR – {result['error']}")
        return result

    time.sleep(1)

    # ------------------------------------------------------------------
    # 6. Click the Documents tab (JS click — href is javascript:void(0))
    # ------------------------------------------------------------------
    try:
        doc_tab = page.locator("a.public-tab[data-handler='dspCaseDocuments']").first
        doc_tab.wait_for(state="attached", timeout=10_000)
        doc_tab.evaluate("el => el.click()")
        print(f"[{case_number}] Clicked Documents tab (data-handler=dspCaseDocuments)")
    except Exception as exc:
        print(f"[{case_number}] WARNING – Documents tab not found: {exc}")
        result["error"] = "Documents tab not found"
        return result

    time.sleep(2)

    # ------------------------------------------------------------------
    # 7. Wait for the documents table to appear
    # ------------------------------------------------------------------
    try:
        page.wait_for_selector("table.table-public", timeout=10_000)
        print(f"[{case_number}] Documents table (table.table-public) found")
    except Exception as exc:
        print(f"[{case_number}] WARNING – documents table not found: {exc}")
        result["error"] = "Documents table not found after clicking Documents tab"
        return result

    time.sleep(1)

    # ------------------------------------------------------------------
    # 8 & 9. Paginate and extract all document rows
    # ------------------------------------------------------------------
    all_documents = []
    page_num = 1

    while True:
        html = page.content()
        docs_on_page = _extract_documents(html)
        all_documents.extend(docs_on_page)
        print(f"[{case_number}] Page {page_num}: extracted {len(docs_on_page)} document(s)")

        # Check for a next-page link (inside a collapsed dropdown — use JS click)
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
            # No more pages
            break

    print(f"[{case_number}] Total extracted: {len(all_documents)} document(s)")
    result["documents"] = all_documents

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    case_numbers = load_case_numbers(args)

    if not case_numbers:
        print("[ERROR] No case numbers provided.")
        sys.exit(1)

    print(f"Cases to process: {case_numbers}")
    print(f"Output file: {args.output}")
    print(f"Headless: {args.headless}")

    all_results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for case_number in case_numbers:
            try:
                result = scrape_case_documents(page, case_number)
            except Exception as exc:
                result = {
                    "case_number": case_number,
                    "scraped_at": datetime.now().isoformat(timespec="seconds"),
                    "documents": [],
                    "error": f"Unhandled exception: {exc}",
                }
                print(f"[{case_number}] UNHANDLED ERROR – {exc}")
            all_results.append(result)

        context.close()
        browser.close()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResults written to: {output_path.resolve()}")

    # Summary
    ok = sum(1 for r in all_results if "error" not in r)
    err = len(all_results) - ok
    print(f"Done. {ok} succeeded, {err} failed.")


if __name__ == "__main__":
    main()

