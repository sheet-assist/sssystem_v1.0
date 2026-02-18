#!/usr/bin/env python
"""
Script to update qualification status for prospects with today's or future auction dates.
"""
import os
import django
from datetime import date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.prospects.models import Prospect

def update_prospects():
    """Update all prospects with today's or future dates to 'pending' qualification status."""
    today = date.today()
    
    # Find all prospects with auction_date >= today
    prospects = Prospect.objects.filter(auction_date__gte=today)
    
    count = prospects.count()
    print(f"Found {count} prospect(s) with today's or future auction dates.")
    
    if count > 0:
        # Update their qualification_status to 'pending'
        updated_count = prospects.update(qualification_status='pending')
        print(f"Successfully updated {updated_count} prospect(s) to 'pending' status.")
        
        # Display the updated prospects
        print("\nUpdated prospects:")
        for prospect in prospects:
            print(f"  - Case #{prospect.case_number} | Date: {prospect.auction_date} | Status: {prospect.qualification_status}")
    else:
        print("No prospects found with today's or future auction dates.")

if __name__ == '__main__':
    update_prospects()
