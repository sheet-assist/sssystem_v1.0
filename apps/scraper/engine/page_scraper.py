"""Playwright-backed helpers for scraping auction pages."""

import random
import time
import re

from bs4 import BeautifulSoup

from .url_utils import build_auction_url


LABEL_REGEX_MAP = {
    r"auction\s*type": "auction_type",
    r"case\s*#|case\s*number": "case_number",
    r"final\s*judgment": "final_judgment_amount",
    r"parcel\s*id": "parcel_id",
    r"property\s*address": "property_address",
    r"assessed\s*value": "assessed_value",
    r"plaintiff\s*max\s*bid": "plaintiff_max_bid",
    r"opening\s*bid": "opening_bid",
    
}


def _normalize_label(text):
    """Normalize raw label text so regex matching stays reliable."""
    if not text:
        return ""

    cleaned = text.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[:]+$", "", cleaned).strip()
    return cleaned.lower()


def scrape_single_date(page, base_url, auction_date, log_fn):
    """Scrape auctions for a single date using an existing Playwright page."""
    url = build_auction_url(base_url, auction_date)
    print(f"Navigating to {url}")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # print("Page loaded,, waiting for auction items...")
    except Exception as exc:
        print(f"Failed to navigate to {url}: {exc}")
        return [], url

    time.sleep(random.uniform(1, 2))

    try:
        page.wait_for_selector(".AUCTION_ITEM", timeout=10000)
    except Exception:
        print(f"No auctions found for {auction_date}")
        return [], url

    def get_total_pages():
        try:
            max_pages_span = page.locator("#maxCB").first
            if max_pages_span:
                total_text = max_pages_span.text_content(timeout=5000)
                if total_text:
                    total_text = total_text.strip()
                    match = re.search(r"\d+", total_text)
                    if match:
                        return int(match.group())
        except Exception as exc:
            print(f"Could not extract max pages: {exc}")
        return 1

    try:
        raw_auctions = []
        current_page = 1
        max_pages = get_total_pages()
        print(f"Total pages detected: {max_pages}")

        while current_page <= max_pages:
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            for item in soup.select(".AUCTION_ITEM"):
                auction_id = item.get("aid", "")
                status_elem = item.select_one(".ASTAT_MSGB")
                start_time = status_elem.get_text(strip=True) if status_elem else ""

                auction_status = ""
                # if start_time and ("Canceled" in start_time or "Cancelled" in start_time):
                    
                #     auction_status = start_time.strip()
                #     # auction_status = "cancelled"
                #     start_time = "" 
                # elif start_time and "Postponed" in start_time:
                #     auction_status = "postponed"
                #     start_time = ""
                if start_time and not re.search(r"\d", start_time):
                    # start_time holds a textual status, so treat it as such
                    auction_status = start_time.strip()
                    start_time = ""

                

                record = {
                    "auction_id": auction_id,
                    "start_time": start_time,
                    "auction_type": "",
                    "case_number": "",
                    "final_judgment_amount": None,
                    "parcel_id": "",
                    "property_address": "",
                    "city_state_zip": "",
                    "assessed_value": None,
                    "plaintiff_max_bid": None,
                    "auction_status": auction_status,
                    "sold_amount": None,
                    "sold_to": "",
                    "opening_bid": None,
                }

                for row in item.select(".AUCTION_DETAILS table.ad_tab tr"):
                    tds = row.select("td")
                    if len(tds) < 2:
                        continue

                    raw_label = _normalize_label(tds[0].get_text(" ", strip=True))
                    value = tds[1].get_text(" ", strip=True).replace("\xa0", " ").strip()

                    if raw_label == "":
                        record["city_state_zip"] = value
                        continue

                    for pattern, field_name in LABEL_REGEX_MAP.items():
                        if re.search(pattern, raw_label, re.IGNORECASE):
                            record[field_name] = value
                            break

                auction_stats = item.select_one(".AUCTION_STATS")
                # if auction_stats:
                #     auction_status_elem = auction_stats.select_one(".ASTAT_MSGB Astat_DATA")
                #     if auction_status_elem:
                #         auction_status = auction_status_elem.get_text(strip=True)
                

                if auction_status == "":
                    auction_status="Sold"
                    record["auction_status"] = "Sold"

                    if auction_stats:
                        sold_amount = auction_stats.select_one(".ASTAT_MSGD")
                        sold_to = auction_stats.select_one(".ASTAT_MSG_SOLDTO_MSG")

                        if sold_amount:
                            record["sold_amount"] = sold_amount.get_text(strip=True)
                        if sold_to:
                            record["sold_to"] = sold_to.get_text(strip=True)
                
                        
                print(f"Auction ID {auction_id} has status '{auction_status}'"  )     

                raw_auctions.append(record)

            print(f"Parsed {len(soup.select('.AUCTION_ITEM'))} items on page {current_page}")

            if current_page < max_pages:
                try:
                    next_page_num = current_page + 1
                    # print(f"Navigating to page {next_page_num} using input box...")

                    page_input = page.locator("#curPCB").first
                    if page_input:
                        page_input.fill(str(next_page_num))
                        page_input.press("Enter")
                        time.sleep(random.uniform(1, 2))
                        page.wait_for_selector(".AUCTION_ITEM", timeout=20000)
                        current_page += 1
                    else:
                        print("Could not find pagination input box (#curPCB)")
                        break

                except Exception as exc:
                    print(f"Error navigating to next page: {exc}")
                    log_fn("warning", f"Could not navigate to next page for {auction_date}: {exc}")
                    break
            else:
                break

        print(
            f"Parsed total {len(raw_auctions)} auctions from {auction_date} across {current_page} pages"
        )
        return raw_auctions, url

    except Exception as exc:
        print(f"Error parsing page content: {exc}")
        import traceback

        traceback.print_exc()
        return [], url
