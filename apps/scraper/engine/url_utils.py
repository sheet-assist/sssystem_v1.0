"""Helpers for resolving the correct auction URLs for a scrape job."""

from urllib.parse import urlparse, urlunparse

from apps.scraper.models import CountyScrapeURL


REALFORECLOSE_DOMAINS = (".realforeclose.com", ".realtaxdeed.com")


def normalize_base_url(url):
    """Force HTTPS, strip trailing slashes, and drop www for known auction domains."""
    if not url:
        raise ValueError("Base URL is missing.")

    raw = url.strip()
    if not raw:
        raise ValueError("Base URL is missing.")

    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    netloc = parsed.netloc
    path = parsed.path or ""

    if not netloc:
        raise ValueError(f"Invalid base URL '{url}'.")

    hostname = netloc.lower()
    if hostname.startswith("www.") and hostname.endswith(REALFORECLOSE_DOMAINS):
        netloc = netloc[4:]

    normalized = urlunparse(("https", netloc, path.rstrip("/"), "", "", ""))
    return normalized.rstrip("/")


def get_base_url(county, job_type):
    """Retrieve the active base URL for a county/job type, falling back to legacy fields."""
    print(f"Getting base URL for {county} and job type {job_type}")

    try:
        url_obj = CountyScrapeURL.objects.get(
            county=county,
            url_type=job_type,
            is_active=True,
        )
        return normalize_base_url(url_obj.base_url)
    except CountyScrapeURL.DoesNotExist:
        pass

    if job_type == "TD":
        url = getattr(county, "taxdeed_url", None)
    else:
        url = getattr(county, "foreclosure_url", None)

    if not url:
        raise ValueError(
            f"No URL configured for county {county.name} with job type {job_type}. "
            "Add it in County Scrape URLs admin."
        )
    return normalize_base_url(url)


def build_auction_url(base_url, auction_date):
    """Build a calendar URL for the provided auction date."""
    date_str = auction_date.strftime("%m/%d/%Y")
    print(f"Building auction URL with base {base_url} and date {date_str}")
    return (
        f"{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW"
        f"&AUCTIONDATE={date_str}"
    )
