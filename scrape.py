import requests
import re
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import date, timedelta
from playwright.sync_api import sync_playwright
import time

CSV_FILE = "miami_auctions.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

LABEL_REGEX_MAP = {
    r"auction\s*type": "Auction Type",
    r"case\s*#|case\s*number": "Case #",
    r"final\s*judgment": "Final Judgment Amount",
    r"opening\s*bid": "Opening Bid",
    r"parcel\s*id": "Parcel ID",
    r"property\s*address": "Property Address",
    r"assessed\s*value": "Assessed Value",
    r"plaintiff\s*max\s*bid": "Plaintiff Max Bid",
}


def get_total_pages(page):
    """Extract total pages from the pagination element"""
    try:
        # Look for span with id="maxCB" which contains total pages
        max_pages_span = page.locator("#maxCB").first
        if max_pages_span:
            total_text = max_pages_span.text_content(timeout=5000)
            if total_text:
                total_text = total_text.strip()
                match = re.search(r'\d+', total_text)
                if match:
                    return int(match.group())
    except:
        pass
    
    return 1


def scrape_page(page, auction_date, base_url, state, county):
    """Scrape auction data from current page"""
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    auctions = soup.select(".AUCTION_ITEM")

    rows = []
    
    url = (
        f"{base_url}/index.cfm"
        f"?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={auction_date}"
    )

    for a in auctions:
        auction_id = a.get("aid", "")

        start_time = (
            a.select_one(".ASTAT_MSGB").get_text(strip=True)
            if a.select_one(".ASTAT_MSGB")
            else ""
        )
        status=""
        if start_time.find("Canceled") >=0 :
            status=start_time
            start_time=""

        record = {
            "state" :state,
            "county": county,
            

            "Auction Date": auction_date,
            "Auction ID": auction_id,
            "Start Time": start_time,
            "Auction Type": "",
            "Case #": "",
            "Final Judgment Amount": "",
            "Opening Bid": "",
            "Parcel ID": "",
            "Property Address": "",
            "City/State/Zip": "",
            "Assessed Value": "",
            "Plaintiff Max Bid": "",
            "Status": status,
            "Sold Amount": "",
            "Sold To": "",
            "auction_url":url

        }

        # -------- AUCTION DETAILS (Regex based) --------
        for row in a.select(".AUCTION_DETAILS table.ad_tab tr"):
            tds = row.select("td")
            if len(tds) < 2:
                continue

            raw_label = tds[0].get_text(" ", strip=True).lower()
            value = tds[1].get_text(" ", strip=True)

            if raw_label == "":
                record["City/State/Zip"] = value
                continue

            for pattern, field in LABEL_REGEX_MAP.items():
                if re.search(pattern, raw_label, re.IGNORECASE):
                    record[field] = value
                    break

        # -------- SOLD DETAILS --------
        auction_stats = a.select_one(".AUCTION_STATS")
        if status=="":
            record["Status"] = "Sold"

            sold_amount = auction_stats.select_one(".ASTAT_MSGD")
            sold_to = auction_stats.select_one(".ASTAT_MSG_SOLDTO_MSG")

            if sold_amount:
                record["Sold Amount"] = sold_amount.get_text(strip=True)
            if sold_to:
                record["Sold To"] = sold_to.get_text(strip=True)

        rows.append(record)

    return rows


def rundates(page, auction_date, base_url, state, county):
    url = (
        f"{base_url}/index.cfm"
        f"?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={auction_date}"
    )

    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector(".AUCTION_ITEM", timeout=20000)
    except:
        print(f"⚠ No auctions found for {auction_date}")
        return

    total_pages = get_total_pages(page)
    print(f"📄 Total pages for {auction_date}: {total_pages}")

    all_rows = []
    current_page = 1

    while current_page <= total_pages:
        print(f"  Scraping page {current_page}/{total_pages}...")
        
        rows = scrape_page(page, auction_date, base_url, state, county)
        all_rows.extend(rows)

        if current_page < total_pages:
            # Navigate to next page using input box
            try:
                page_input = page.locator("#curPCB").first
                if page_input:
                    next_page_num = current_page + 1
                    print(f"  Navigating to page {next_page_num} using input box...")
                    page_input.fill(str(next_page_num))
                    page_input.press("Enter")
                    
                    # Wait for page content to load
                    page.wait_for_selector(".AUCTION_ITEM", timeout=20000)
                    time.sleep(1)  # Small delay to ensure content is rendered
                else:
                    print(f"⚠ Could not find pagination input box (#curPCB)")
                    break
                
            except Exception as e:
                print(f"⚠ Error navigating to next page: {e}")
                break

        current_page += 1

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv(
            CSV_FILE,
            mode="a",
            index=False,
            header=not os.path.exists(CSV_FILE)
        )

    print(f"✅ {len(all_rows)} total records saved for {auction_date}")


def run_auctions(start_date, end_date, base_url, state, county):
    """
    start_date : datetime.date
    end_date   : datetime.date (exclusive)
    base_url   : county foreclosure site base URL
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            extra_http_headers={**HEADERS, "Referer": base_url}
        )

        current_date = start_date
        while current_date < end_date:
            rundates(
                page,
                current_date.strftime("%m/%d/%Y"),
                base_url, state, county
            )
            current_date += timedelta(days=1)

        browser.close()


if __name__ == "__main__":
    # Scrape Miami-Dade for 10/23/2025
    base_url = "https://www.miamidade.realforeclose.com"
    state = "FL"
    county = "Miami-Dade"
    start_date = date(2025, 10, 27)
    end_date = date(2025, 10, 28)  # Exclusive, so this scrapes only 10/23
    
    print("🚀 Starting Miami-Dade Foreclosure Scraper...")
    run_auctions(start_date, end_date, base_url, state, county)
    print("✅ Scraping complete!")



