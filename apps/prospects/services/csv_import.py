import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError

from apps.prospects.models import Prospect, log_prospect_action

REQUIRED_COLUMNS = {"case_number", "prospect_type", "auction_date"}

VALID_PROSPECT_TYPES = {code for code, _ in Prospect.PROSPECT_TYPES}

VALID_AUCTION_STATUSES = {code for code, _ in Prospect.AUCTION_STATUS_CHOICES}

COLUMN_MAP = {
    "case_number": "case_number",
    "prospect_type": "prospect_type",
    "auction_date": "auction_date",
    "case_style": "case_style",
    "property_address": "property_address",
    "city": "city",
    "zip_code": "zip_code",
    "parcel_id": "parcel_id",
    "final_judgment_amount": "final_judgment_amount",
    "opening_bid": "opening_bid",
    "assessed_value": "assessed_value",
    "plaintiff_name": "plaintiff_name",
    "defendant_name": "defendant_name",
    "auction_status": "auction_status",
    "auction_time": "auction_time",
    "sale_amount": "sale_amount",
    "sold_to": "sold_to",
}

DECIMAL_FIELDS = {"final_judgment_amount", "opening_bid", "assessed_value", "sale_amount"}

TEXT_FIELDS = {
    "case_number", "case_style", "property_address", "city",
    "zip_code", "parcel_id", "plaintiff_name", "defendant_name",
}
TEXT_FIELDS = TEXT_FIELDS.union({"sold_to"})


def _parse_date(value):
    """Parse a date string in YYYY-MM-DD or MM/DD/YYYY format."""
    if not value or not value.strip():
        return None
    stripped = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(value):
    """Parse a time string in HH:MM format."""
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return None


def _parse_decimal(value):
    """Parse a decimal value, stripping currency symbols and commas."""
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _validate_row(row_num, row, headers):
    """Validate a single CSV row. Returns (cleaned_data, errors)."""
    errors = []
    data = {}

    # Check required fields
    for col in REQUIRED_COLUMNS:
        val = row.get(col, "").strip()
        if not val:
            errors.append(f"Row {row_num}: Missing required field '{col}'")

    if errors:
        return None, errors

    # Validate prospect_type
    pt = row.get("prospect_type", "").strip().upper()
    if pt not in VALID_PROSPECT_TYPES:
        errors.append(
            f"Row {row_num}: Invalid prospect_type '{row.get('prospect_type', '')}'. "
            f"Must be one of: {', '.join(sorted(VALID_PROSPECT_TYPES))}"
        )
    else:
        data["prospect_type"] = pt

    # Validate auction_date
    auction_date = _parse_date(row.get("auction_date", ""))
    if auction_date is None:
        errors.append(
            f"Row {row_num}: Invalid auction_date '{row.get('auction_date', '')}'. "
            f"Expected format: MM/DD/YYYY or YYYY-MM-DD"
        )
    else:
        data["auction_date"] = auction_date

    if errors:
        return None, errors

    # Text fields
    for col in TEXT_FIELDS:
        if col in headers:
            data[col] = row.get(col, "").strip()

    # Decimal fields
    for col in DECIMAL_FIELDS:
        if col in headers:
            raw = row.get(col, "").strip()
            if raw:
                val = _parse_decimal(raw)
                if val is None:
                    errors.append(
                        f"Row {row_num}: Invalid number for '{col}': '{raw}'"
                    )
                else:
                    data[col] = val

    # Auction status
    if "auction_status" in headers:
        status_val = row.get("auction_status", "").strip()
        if status_val:
            if status_val not in VALID_AUCTION_STATUSES:
                errors.append(
                    f"Row {row_num}: Invalid auction_status '{status_val}'. "
                    f"Must be one of: {', '.join(sorted(VALID_AUCTION_STATUSES))}"
                )
            else:
                data["auction_status"] = status_val

    # Auction time
    if "auction_time" in headers:
        time_raw = row.get("auction_time", "").strip()
        if time_raw:
            parsed_time = _parse_time(time_raw)
            if parsed_time is None:
                errors.append(
                    f"Row {row_num}: Invalid auction_time '{time_raw}'. Expected format: HH:MM"
                )
            else:
                data["auction_time"] = parsed_time

    if errors:
        return None, errors

    return data, []


def import_prospects_from_csv(csv_file, county, uploaded_by, source=None, upload_log=None):
    """
    Import prospects from an uploaded CSV file.

    Args:
        csv_file: An uploaded file object (InMemoryUploadedFile or similar).
        county: A County model instance.
        uploaded_by: The User who triggered the upload.

    Returns:
        dict with keys: created (int), skipped (int), errors (list of dicts).
    """
    result = {"created": 0, "skipped": 0, "errors": []}
    result["total_rows"] = 0

    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        result["errors"].append({"row": 0, "message": "File is not valid UTF-8 encoded text."})
        return result

    reader = csv.DictReader(io.StringIO(content))

    if reader.fieldnames is None:
        result["errors"].append({"row": 0, "message": "CSV file is empty or has no header row."})
        return result

    # Normalize headers
    headers = {h.strip().lower() for h in reader.fieldnames}

    # Check required columns
    missing = REQUIRED_COLUMNS - headers
    if missing:
        result["errors"].append({
            "row": 0,
            "message": f"Missing required columns: {', '.join(sorted(missing))}",
        })
        return result

    for row_num, row in enumerate(reader, start=2):  # row 1 is header
        result["total_rows"] += 1
        # Normalize keys
        row = {k.strip().lower(): v for k, v in row.items() if k}

        data, row_errors = _validate_row(row_num, row, headers)
        if row_errors:
            for err in row_errors:
                result["errors"].append({"row": row_num, "message": err})
            continue

        # Build prospect kwargs
        prospect_kwargs = {"county": county, "state": county.state.abbreviation}
        if source:
            prospect_kwargs["source"] = source
        for csv_col, model_field in COLUMN_MAP.items():
            if csv_col in data:
                prospect_kwargs[model_field] = data[csv_col]

        # Derive surplus_amount when sale_amount and at least one liability field are present.
        # For Tax Deed (TD) use sale_amount - opening_bid. Otherwise prefer
        # final_judgment_amount, then plaintiff_max_bid, then opening_bid.
        sale_amt = prospect_kwargs.get("sale_amount")
        if sale_amt is not None:
            try:
                pt = (prospect_kwargs.get("prospect_type") or "").upper()
            except Exception:
                pt = ""

            surplus_val = None
            if pt == "TD":
                ob = prospect_kwargs.get("opening_bid")
                if ob is not None:
                    surplus_val = sale_amt - ob
            else:
                liability = None
                if prospect_kwargs.get("final_judgment_amount") is not None:
                    liability = prospect_kwargs.get("final_judgment_amount")
                elif prospect_kwargs.get("plaintiff_max_bid") is not None:
                    liability = prospect_kwargs.get("plaintiff_max_bid")
                elif prospect_kwargs.get("opening_bid") is not None:
                    liability = prospect_kwargs.get("opening_bid")
                if liability is not None:
                    surplus_val = sale_amt - liability

            if surplus_val is not None:
                prospect_kwargs["surplus_amount"] = surplus_val

        try:
            if upload_log is not None:
                prospect_kwargs["uploaded_from"] = upload_log
            prospect = Prospect.objects.create(**prospect_kwargs)
            log_prospect_action(
                prospect=prospect,
                user=uploaded_by,
                action_type="created",
                description="Created via CSV upload",
            )
            result["created"] += 1
        except IntegrityError:
            result["skipped"] += 1

    return result
