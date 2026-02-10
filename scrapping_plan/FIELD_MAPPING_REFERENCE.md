# Field Mapping: Auction Data → Prospects Model

**Reference Guide for Phase 2 Implementation**

---

## Overview

This document specifies how auction scraper data maps to the Prospects model during Phase 2 implementation.

---

## Direct Field Mappings

### 1:1 Field Mapping (Auto-match by Name)

| Auction Scraper Field | Prospect Model Field | Data Type | Notes |
|------------------------|----------------------|-----------|-------|
| auction_date | auction_date | DateField | Date of auction happening |
| property_address | address | CharField | Full property address |
| status | status | CharField | Sold, Canceled, Failed, etc. |
| auction_type | type | CharField | Foreclosure type |

---

## Financial Amount Mappings

### Convert & Clean Currency Strings

| Auction Field | Target Field | Processing |
|---------------|--------------|------------|
| final_judgment_amount | (judgment_amount) | Parse: "$1,234.56" → 1234.56 |
| plaintiff_max_bid | (plaintiff_bid) | Parse: "$2,000.00" → 2000.00 |
| assessed_value | (assessed_value) | Parse: "$500,000" → 500000.0 |
| sold_amount | (sale_price/amount) | Parse: "$750,000.00" → 750000.00 |

**Parsing Logic**:
```python
import re

def parse_currency(value):
    """Convert '$1,234.56' to 1234.56"""
    if not value:
        return None
    # Remove $, commas, spaces
    cleaned = re.sub(r'[$,\s]', '', value)
    try:
        return float(cleaned)
    except ValueError:
        return None
```

---

## Complex Mappings

### Location Information

| Auction Field | Target | Strategy |
|---------------|--------|----------|
| city/state/zip | address | Append to property_address if separate fields exist |
| county | (infer from job) | Get from ScrapingJob.county |
| state | (infer from job) | Get from ScrapingJob.state |

### Auction Details

| Auction Field | Target | Notes |
|---------------|--------|-------|
| auction_id | (auction_reference) | Store as string for traceability |
| case# | (case_number) | Store if Prospects model has field |
| parcel_id | (parcel_id) | Store if available |
| start_time | (auction_time) | Store separately if needed |

### Audit & Tracking

| Auction Field | Target | Value |
|---------------|--------|-------|
| auction_url | (source_url) | Full URL to original auction page |
| created_by (job) | created_by | User who ran the scraper job |
| scraped_at | created_at | Timestamp when record created |
| job_id | (job_reference) | FK or reference to ScrapingJob |

---

## Implementation Code Template

```python
# apps/scraper/services/job_service.py

def save_to_prospects(auction_records, job_id):
    """
    Convert auction scraper records to Prospect model instances.
    
    Args:
        auction_records: List of dicts from scraper
        job_id: ScrapingJob UUID
    
    Returns:
        List of created Prospect objects
    """
    from apps.prospects.models import Prospect
    from apps.scraper.models import ScrapingJob
    
    job = ScrapingJob.objects.get(id=job_id)
    prospects = []
    
    for record in auction_records:
        # Parse dates
        auction_date = parse_date(record.get('Auction Date'))
        
        # Parse amounts
        judgment = parse_currency(record.get('Final Judgment Amount'))
        sold_amount = parse_currency(record.get('Sold Amount'))
        assessed = parse_currency(record.get('Assessed Value'))
        
        # Create Prospect
        prospect = Prospect(
            # Direct mappings
            auction_date=auction_date,
            address=record.get('Property Address'),
            status=record.get('Status'),
            type=record.get('Auction Type'),
            
            # Amount fields
            judgment_amount=judgment,
            sale_price=sold_amount,
            assessed_value=assessed,
            
            # Location (from job)
            county=job.county,
            state=job.state,
            
            # Audit trail
            source_url=record.get('auction_url'),
            created_by=job.created_by,
            job_reference=str(job.id),  # Link back to job
        )
        prospects.append(prospect)
    
    # Bulk create for performance
    return Prospect.objects.bulk_create(prospects, batch_size=1000)
```

---

## Field Validation Rules

### Required Fields (Must Not Be Null)

- **auction_date**: Use job.start_date if missing
- **address**: Skip record if empty
- **status**: Default to 'Unknown' if missing

### Optional Fields (Can Be Null)

- **judgment_amount**, **sale_price**, **assessed_value**: May not be available
- **case_number**, **parcel_id**: Optional for some auctions
- **plaintiff_bid**: Only if auction not sold

### Validation Logic

```python
def validate_auction_record(record):
    """Validate required fields."""
    if not record.get('Property Address'):
        return False, "Missing address"
    if not record.get('Auction Date'):
        return False, "Missing date"
    return True, None
```

---

## Data Type Transformations

### String Cleaning

- Trim whitespace
- Normalize dates: 'MM/DD/YYYY' → YYYY-MM-DD
- Normalize case: 'Sold' → 'sold' (if lowercase needed)

### Amount Normalization

- Currency: Parse and convert to float
- Validation: Reject if > $1 million but address suggests residential

### Status Normalization

**Raw Status** → **Normalized**
- "Sold" → "sold"
- "Canceled" → "canceled"
- "Failed" → "failed"  
- "Pending" → "pending"

---

## Performance Considerations

### Batch Processing

```python
# Don't create one by one
# for record in records:
#     Prospect.objects.create(...)  # BAD - N queries

# Instead, batch create
prospects = [Prospect(...) for record in records]
Prospect.objects.bulk_create(prospects, batch_size=1000)  # GOOD - 1 query
```

### Database Indexes

Recommend adding indexes to:
- `auction_date` (frequently filtered)
- `status` (filtering)
- `address` (searching)
- `job_reference` (lookups)

---

## Testing the Mapping

```python
# apps/scraper/tests/test_mapping.py

def test_auction_to_prospect_mapping():
    """Verify auction records convert correctly to prospects."""
    # Sample auction record from scraper
    auction = {
        'Auction Date': '02/15/2026',
        'Property Address': '123 Main St, Miami, FL',
        'Auction Type': 'Foreclosure',
        'Status': 'Sold',
        'Final Judgment Amount': '$250,000.00',
        'Sold Amount': '$350,000.00',
    }
    
    # Convert
    prospect = convert_auction_to_prospect(auction)
    
    # Assert
    assert prospect.auction_date == date(2026, 2, 15)
    assert prospect.address == '123 Main St, Miami, FL'
    assert prospect.type == 'Foreclosure'
    assert prospect.status == 'Sold'
    assert prospect.judgment_amount == 250000.0
    assert prospect.sale_price == 350000.0
```

---

## Prospect Model Fields (Expected)

Based on survey responses, the Prospects model should have:

```python
class Prospect(models.Model):
    # Core fields
    auction_date = models.DateField()
    address = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    type = models.CharField(max_length=50)
    
    # Financial fields
    judgment_amount = models.DecimalField(decimal_places=2, max_digits=12, null=True)
    sale_price = models.DecimalField(decimal_places=2, max_digits=12, null=True)
    assessed_value = models.DecimalField(decimal_places=2, max_digits=12, null=True)
    plaintiff_bid = models.DecimalField(decimal_places=2, max_digits=12, null=True)
    
    # Location fields
    county = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=2, null=True)
    parcel_id = models.CharField(max_length=50, null=True)
    case_number = models.CharField(max_length=50, null=True)
    
    # Audit fields
    source_url = models.URLField(null=True)
    job_reference = models.CharField(max_length=36, null=True)  # UUID as string
    created_by = models.ForeignKey(User, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## Next Steps (Phase 2)

1. ✅ Verify Prospect model structure (confirm all fields)
2. ✅ Create `save_to_prospects()` function in job_service.py
3. ✅ Add validation and error handling
4. ✅ Test with sample auction data
5. ✅ Integrate into async job execution
6. ✅ Add CSV export alongside Prospects creation

---

## Questions?

Refer to [scraper_plan.md](scraper_plan.md) Section 14 for overview, or contact project lead.
