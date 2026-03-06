#!/usr/bin/env python
"""Debug script to test invoice grouping in all contexts"""
import os
import sys
import django
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from clients.models import Client
from invoices.models import Invoice
from invoices.utils import build_invoice_items_list, render_invoice_tex
from timesheets.models import TimesheetEntry, WorkCategory

User = get_user_model()

def test_grouping():
    """Test grouping in all contexts"""
    
    # Get or create test user
    try:
        user = User.objects.get(username='testdebug')
        user.delete()  # Fresh start
    except:
        pass
    
    user = User.objects.create_user(username='testdebug', email='testdebug@example.com', password='password')
    from core.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.initial_setup_complete = True
    profile.save()
    
    # Create client
    client = Client.objects.create(user=user, name="Test Client", email="test@example.com")
    
    # Create invoice
    today = timezone.now().date()
    invoice = Invoice.objects.create(
        user=user,
        client=client,
        number="TEST-001",
        status="DRAFT",
        date_issued=today,
        due_date=today + timedelta(days=14),
        billing_type="SERVICE"
    )
    
    # Create categories
    consulting = WorkCategory.objects.create(user=user, name="Consulting")
    development = WorkCategory.objects.create(user=user, name="Development")
    
    # Create multiple timesheets for the same category
    ts1 = TimesheetEntry.objects.create(
        user=user,
        client=client,
        category=consulting,
        date=today,
        hours=Decimal("3.00"),
        hourly_rate=Decimal("150.00"),
        is_billed=True,
        invoice=invoice,
    )
    
    ts2 = TimesheetEntry.objects.create(
        user=user,
        client=client,
        category=consulting,
        date=today,
        hours=Decimal("2.00"),
        hourly_rate=Decimal("150.00"),
        is_billed=True,
        invoice=invoice,
    )
    
    ts3 = TimesheetEntry.objects.create(
        user=user,
        client=client,
        category=development,
        date=today,
        hours=Decimal("4.00"),
        hourly_rate=Decimal("200.00"),
        is_billed=True,
        invoice=invoice,
    )
    
    invoice.sync_totals()
    
    print("\n✅ TEST DATA CREATED")
    print(f"Invoice {invoice.number} with {invoice.billed_timesheets.count()} timesheets:")
    for ts in invoice.billed_timesheets.all().select_related("category"):
        print(f"  - {ts.category.name}: {ts.hours}h @ ${ts.hourly_rate}/hr")
    
    # Test 1: Check build_invoice_items_list
    print("\n📋 TEST 1: build_invoice_items_list()")
    items = build_invoice_items_list(invoice, is_service=True)
    print(f"Returned {len(items)} item(s):")
    for item in items:
        print(f"  - {item['description']}: {item['quantity']} @ {item['unit_price']} = {item['row_subtotal']}")
    
    # Should have 2 items (Consulting and Development grouped)
    expected_count = 2
    if len(items) == expected_count:
        print(f"✅ Correct count: {expected_count}")
    else:
        print(f"❌ WRONG COUNT: Expected {expected_count}, got {len(items)}")
    
    # Check that Consulting is 5.00 hours
    consulting_item = next((i for i in items if "Consulting" in i["description"]), None)
    if consulting_item and "5.00" in consulting_item["quantity"]:
        print(f"✅ Consulting correctly grouped to 5.00 hours")
    else:
        print(f"❌ Consulting NOT grouped: {consulting_item}")
    
    # Test 2: Check render_invoice_tex
    print("\n📄 TEST 2: render_invoice_tex()")
    tex_content = render_invoice_tex(invoice)
    print(f"LaTeX content length: {len(tex_content)} chars")
    
    if "5.00" in tex_content and "Consulting" in tex_content:
        print("✅ LaTeX contains grouped Consulting (5.00 hours)")
    else:
        print("❌ LaTeX does NOT contain grouped Consulting")
    
    if "4.00" in tex_content and "Development" in tex_content:
        print("✅ LaTeX contains Development (4.00 hours)")
    else:
        print("❌ LaTeX does NOT contain Development")
    
    # Count how many times "hourly_rate" appears in tex (should be 2 for 2 items)
    hourly_rate_count = tex_content.count("150.00") + tex_content.count("200.00")
    if hourly_rate_count >= 2:
        print(f"✅ LaTeX contains rate information")
    else:
        print(f"❌ LaTeX missing rate information")
    
    # Check for ungrouped entries (should NOT see 3.00 or 2.00 individually)
    if "3.00" not in tex_content and "2.00" not in tex_content:
        print("✅ LaTeX does NOT contain individual ungrouped entries (3.00, 2.00)")
    else:
        print("❌ LaTeX contains ungrouped individual entries!")
        if "3.00" in tex_content:
            print("   Found 3.00 hours (ungrouped)")
        if "2.00" in tex_content:
            print("   Found 2.00 hours (ungrouped)")
    
    # Clean up
    user.delete()
    print("\n✅ Test complete and cleaned up")

if __name__ == "__main__":
    test_grouping()
