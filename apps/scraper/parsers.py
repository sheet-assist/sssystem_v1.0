"""
Parsers for realforeclose.com and realtaxdeed.com auction data.
Extracts structured prospect data from HTML — mirrors scrape.py logic.
"""
import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

# Regex-based label mapping (from scrape.py)
LABEL_REGEX_MAP = {
    r"auction\s*type": "auction_type",
    r"case\s*#|case\s*number": "case_number",
    r"final\s*judgment": "final_judgment_amount",
    r"parcel\s*id": "parcel_id",
    r"property\s*address": "property_address",
    r"assessed\s*value": "assessed_value",
    r"plaintiff\s*max\s*bid": "plaintiff_max_bid",
}

CURRENCY_FIELDS = {"final_judgment_amount", "assessed_value", "plaintiff_max_bid"}


def parse_currency(text):
    """Convert currency string like '$1,234.56' to Decimal or None."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.strip())
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_city_state_zip(text):
    """Split 'City, ST 12345' into (city, state, zip)."""
    if not text:
        return "", "", ""
    parts = text.strip().split(",")
    city = parts[0].strip() if parts else ""
    state = ""
    zip_code = ""
    if len(parts) > 1:
        rest = parts[1].strip().split()
        if rest:
            state = rest[0]
        if len(rest) > 1:
            zip_code = rest[1]
    return city, state, zip_code


def parse_calendar_page(html):
    """
    Parse calendar page HTML from realforeclose.com / realtaxdeed.com.
    Returns list of raw auction dicts — one per .AUCTION_ITEM element.
    Mirrors scrape.py rundates() logic exactly.
    """
    soup = BeautifulSoup(html, "html.parser")
    auctions = []

    for item in soup.select(".AUCTION_ITEM"):
        auction_id = item.get("aid", "")

        # Start time / status from .ASTAT_MSGB
        status_elem = item.select_one(".ASTAT_MSGB")
        start_time = status_elem.get_text(strip=True) if status_elem else ""

        # Determine status
        auction_status = ""
        if "Canceled" in start_time or "Cancelled" in start_time:
            auction_status = "cancelled"
            start_time = ""
        elif "Postponed" in start_time:
            auction_status = "postponed"
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
        }

        # ---- AUCTION DETAILS (regex label matching, same as scrape.py) ----
        for row in item.select(".AUCTION_DETAILS table.ad_tab tr"):
            tds = row.select("td")
            if len(tds) < 2:
                continue

            raw_label = tds[0].get_text(" ", strip=True).lower()
            value = tds[1].get_text(" ", strip=True)

            # Empty label = City/State/Zip row
            if raw_label == "":
                record["city_state_zip"] = value
                continue

            for pattern, field_name in LABEL_REGEX_MAP.items():
                if re.search(pattern, raw_label, re.IGNORECASE):
                    if field_name in CURRENCY_FIELDS:
                        record[field_name] = parse_currency(value)
                    else:
                        record[field_name] = value
                    break

        # ---- SOLD DETAILS (from .AUCTION_STATS, same as scrape.py) ----
        auction_stats = item.select_one(".AUCTION_STATS")
        if auction_stats and not auction_status:
            record["auction_status"] = "sold"
            sold_amount_elem = auction_stats.select_one(".ASTAT_MSGD")
            sold_to_elem = auction_stats.select_one(".ASTAT_MSG_SOLDTO_MSG")
            if sold_amount_elem:
                record["sold_amount"] = parse_currency(sold_amount_elem.get_text(strip=True))
            if sold_to_elem:
                record["sold_to"] = sold_to_elem.get_text(strip=True)

        auctions.append(record)

    return auctions


def normalize_prospect_data(raw, auction_date, prospect_type, source_url=""):
    """
    Convert raw parsed auction dict into Prospect-model-compatible dict.
    Maps every field from scrape.py output and converts currency strings to Decimal.
    """
    city, state, zip_code = parse_city_state_zip(raw.get("city_state_zip", ""))

    return {
        "prospect_type": prospect_type,
        "auction_item_number": raw.get("auction_id", ""),
        "case_number": raw.get("case_number", ""),
        "auction_type": raw.get("auction_type", ""),
        "property_address": raw.get("property_address", ""),
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "parcel_id": raw.get("parcel_id", ""),
        "final_judgment_amount": parse_currency(raw.get("final_judgment_amount")),
        "plaintiff_max_bid": parse_currency(raw.get("plaintiff_max_bid")),
        "assessed_value": parse_currency(raw.get("assessed_value")),
        "sale_amount": parse_currency(raw.get("sold_amount")),
        "auction_status": raw.get("auction_status", ""),
        "source_url": source_url,
        "raw_data": raw,
    }
