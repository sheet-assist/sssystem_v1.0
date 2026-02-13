"""Data collection and persistence helpers for scraper jobs."""

from decimal import Decimal

from playwright.sync_api import sync_playwright

from apps.prospects.models import Prospect, add_rule_note
from apps.scraper.parsers import normalize_prospect_data
from apps.settings_app.evaluation import evaluate_prospect

from .config import HEADERS
from .page_scraper import scrape_single_date


def _to_decimal(value):
    """Convert scraped numeric values to Decimal when possible."""
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def collect_scraped_data(job, dates, base_url, log_fn):
    """Collect raw auction data for all requested dates using a single browser session."""
    all_scraped_data = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers={**HEADERS, "Referer": base_url})

        try:
            for auction_date in dates:
                # print(f"Scraping for date: {auction_date}")
                raw_auctions, source_url = scrape_single_date(page, base_url, auction_date, log_fn)
                print("getting results...")
                print(source_url, len(raw_auctions))

                for raw in raw_auctions:
                    try:
                        # print(
                        #     f"Processing auction {raw.get('auction_id')} with case number {raw.get('case_number')}"
                        # )
                        data = normalize_prospect_data(raw, auction_date, job.job_type, source_url)
                        case_number = data.get("case_number")
                        # print(case_number)

                        if case_number:
                            all_scraped_data.append(
                                {
                                    "data": data,
                                    "date": auction_date,
                                    "case_number": case_number,
                                }
                            )
                    except Exception as exc:
                        print(f"Error processing auction: {exc}")
        finally:
            browser.close()

    return all_scraped_data


def persist_scraped_data(job, scraped_items):
    """Upsert Prospect records and evaluate qualification for the scraped items."""
    county = job.county
    created = 0
    updated = 0
    qualified_count = 0
    disqualified_count = 0

    for item in scraped_items:
        try:
            data = item["data"]
            auction_date = item["date"]
            case_number = item["case_number"]

            sale_amount_value = _to_decimal(data.get("sale_amount"))
            final_amount_value = _to_decimal(data.get("final_judgment_amount"))
            opening_bid_value = _to_decimal(data.get("opening_bid"))
            prospect_type = data.get("prospect_type", "")
            surplus_amount_value = Decimal("0")
            print(f"Processing prospect {case_number} of opening bid amount    {opening_bid_value}")
            if sale_amount_value is not None:
                
                if prospect_type == "TD":
                    surplus_amount_value = sale_amount_value - (opening_bid_value or Decimal("0"))
                else:
                    surplus_amount_value = sale_amount_value - (final_amount_value or Decimal("0"))
                print(f"Calculated surplus amount for case {case_number} as {surplus_amount_value}")
            defaults = {
                "prospect_type": data.get("prospect_type", ""),
                "auction_item_number": data.get("auction_item_number", ""),
                "auction_type": data.get("auction_type", ""),
                "property_address": data.get("property_address", ""),
                "city": data.get("city", ""),
                "state": data.get("state", ""),
                "zip_code": data.get("zip_code", ""),
                "parcel_id": data.get("parcel_id", ""),
                "final_judgment_amount": final_amount_value,
                "plaintiff_max_bid": data.get("plaintiff_max_bid"),
                "assessed_value": data.get("assessed_value"),
                "sale_amount": sale_amount_value,
                "surplus_amount": surplus_amount_value,
                "sold_to": data.get("sold_to", ""),
                "auction_status": data.get("auction_status", ""),
                "source_url": data.get("source_url", ""),
                "raw_data": data.get("raw_data", {}),
                "opening_bid": opening_bid_value,
            }
            # sold_data = data.get("sold_to", "")
            # print(f"Upserting prospect with sold to-----------------------: {sold_data}")

            prospect, is_new = Prospect.objects.get_or_create(
                county=county,
                case_number=case_number,
                auction_date=auction_date,
                defaults=defaults,
            )

            if is_new:
                created += 1
            else:
                for field in (
                    "auction_status",
                    "sale_amount",
                    "surplus_amount",
                    "sold_to",
                    "property_address",
                    "city",
                    "state",
                    "zip_code",
                    "assessed_value",
                    "final_judgment_amount",
                    "plaintiff_max_bid",
                    "auction_type",
                    "opening_bid",
                ):
                    if field == "sale_amount":
                        val = sale_amount_value
                    elif field == "final_judgment_amount":
                        val = final_amount_value
                    elif field == "surplus_amount":
                        val = surplus_amount_value
                    elif field == "opening_bid":
                        val = opening_bid_value      
                    else:
                        val = data.get(field)
                    if val not in (None, ""):
                        setattr(prospect, field, val)
                prospect.raw_data = data.get("raw_data", {})
                prospect.save()
                updated += 1

            is_qualified, reasons = evaluate_prospect(data, county)
            prospect.qualification_status = "qualified" if is_qualified else "disqualified"
            prospect.save(update_fields=["qualification_status"])

            if is_qualified:
                qualified_count += 1
                add_rule_note(
                    prospect,
                    note="Automated evaluation marked this prospect as qualified.",
                    created_by=None,
                    rule_name="Auto Evaluation",
                    source="scraper",
                    decision="qualified",
                )
            else:
                disqualified_count += 1
                add_rule_note(
                    prospect,
                    note="Automated evaluation marked this prospect as disqualified.",
                    reasons=reasons,
                    created_by=None,
                    rule_name="Auto Evaluation",
                    source="scraper",
                    decision="disqualified",
                )

        except Exception as exc:
            print(f"Error saving prospect: {exc}")
            print(f"Data keys available: {list(data.keys()) if 'data' in locals() else 'N/A'}")

    return {
        "created": created,
        "updated": updated,
        "qualified": qualified_count,
        "disqualified": disqualified_count,
    }
