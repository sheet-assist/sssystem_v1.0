"""
Parsers for realforeclose.com and realtaxdeed.com auction data.
Extracts structured prospect data from HTML.
"""
import re
from decimal import Decimal
from datetime import datetime
from bs4 import BeautifulSoup


LABEL_REGEX_MAP = {
    r"auction\s*type": "Auction Type",
    r"case\s*#|case\s*number": "Case #",
    r"final\s*judgment": "Final Judgment Amount",
    r"parcel\s*id": "Parcel ID",
    r"property\s*address": "Property Address",
    r"assessed\s*value": "Assessed Value",
    r"plaintiff\s*max\s*bid": "Plaintiff Max Bid",
}


def parse_currency(text):
    """Convert currency string (e.g., '$1,234.56') to Decimal."""
    if not text:
        return None
    text = re.sub(r'[^\d.]', '', text.strip())
    try:
        return Decimal(text)
    except:
        return None


def parse_calendar_page(html, county_code):
    """
    Parse calendar page HTML from realforeclose.com.
    Returns list of auction dicts for the calendar.
    """
    soup = BeautifulSoup(html, 'html.parser')
    auctions = []
    
    # Find auction item divs (class AUCTION_ITEM)
    for item in soup.select('.AUCTION_ITEM'):
        auction_id = item.get('aid', '')
        
        # Extract start time and status
        status_elem = item.select_one('.ASTAT_MSGB')
        start_time = status_elem.get_text(strip=True) if status_elem else ''
        
        record = {
            'auction_id': auction_id,
            'start_time': start_time,
            'county_code': county_code,
            'auction_type': '',
            'case_number': '',
            'final_judgment_amount': None,
            'parcel_id': '',
            'property_address': '',
            'city_state_zip': '',
            'assessed_value': None,
            'plaintiff_max_bid': None,
            'auction_status': 'scheduled',
            'sold_amount': None,
            'sold_to': '',
        }
        
        # Check for canceled status
        if 'Canceled' in start_time or 'Postponed' in start_time:
            record['auction_status'] = 'canceled' if 'Canceled' in start_time else 'postponed'
            start_time = ''
        
        # Parse auction details table
        for row in item.select('.AUCTION_DETAILS table.ad_tab tr'):
            tds = row.select('td')
            if len(tds) < 2:
                continue
            
            raw_label = tds[0].get_text(' ', strip=True).lower()
            value = tds[1].get_text(' ', strip=True)
            
            # City/State/Zip is empty label
            if raw_label == '':
                record['city_state_zip'] = value
                continue
            
            # Match label to known fields
            for regex_pattern, field_name in LABEL_REGEX_MAP.items():
                if re.search(regex_pattern, raw_label):
                    if field_name == 'Auction Type':
                        record['auction_type'] = value
                    elif field_name == 'Case #':
                        record['case_number'] = value
                    elif field_name == 'Final Judgment Amount':
                        record['final_judgment_amount'] = parse_currency(value)
                    elif field_name == 'Parcel ID':
                        record['parcel_id'] = value
                    elif field_name == 'Property Address':
                        record['property_address'] = value
                    elif field_name == 'Assessed Value':
                        record['assessed_value'] = parse_currency(value)
                    elif field_name == 'Plaintiff Max Bid':
                        record['plaintiff_max_bid'] = parse_currency(value)
                    break
        
        auctions.append(record)
    
    return auctions


def normalize_prospect_data(raw_data, auction_date, prospect_type='TD'):
    """
    Normalize raw auction data to prospect model fields.
    raw_data: dict from parse_calendar_page
    auction_date: datetime.date
    """
    return {
        'prospect_type': prospect_type,
        'auction_item_number': raw_data.get('auction_id', ''),
        'case_number': raw_data.get('case_number', ''),
        'case_style': '',  # Not extracted from calendar page
        'county_code': raw_data.get('county_code'),
        'property_address': raw_data.get('property_address', ''),
        'city': raw_data.get('city_state_zip', '').split(',')[0].strip() if raw_data.get('city_state_zip') else '',
        'state': 'FL',
        'zip_code': '',
        'parcel_id': raw_data.get('parcel_id', ''),
        'final_judgment_amount': raw_data.get('final_judgment_amount'),
        'opening_bid': None,
        'plaintiff_max_bid': raw_data.get('plaintiff_max_bid'),
        'assessed_value': raw_data.get('assessed_value'),
        'auction_date': auction_date,
        'auction_status': raw_data.get('auction_status', 'scheduled'),
        'plaintiff_name': '',
        'defendant_name': '',
        'property_type': '',
        'legal_description': '',
        'source_url': '',
        'raw_data': raw_data,
    }


def calculate_surplus(prospect_data):
    """
    Estimate surplus amount: sale_amount - opening_bid - costs.
    For now, just use assessed_value - opening_bid as proxy.
    """
    assessed_val = prospect_data.get('assessed_value')
    opening_bid = prospect_data.get('opening_bid')
    
    if assessed_val and opening_bid:
        return assessed_val - opening_bid
    
    return None
