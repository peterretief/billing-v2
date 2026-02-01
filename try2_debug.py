import sys

from django.contrib.auth import get_user_model

from invoices.models import Invoice
from items.models import Item
from items.services import import_recurring_to_invoices


def log(msg):
    print(f">>> [DEBUG] {msg}")
    sys.stdout.flush()

log("Starting the Item-driven Billing Test...")

# 1. Fetch User
User = get_user_model()
target_username = 'peter' 
user = User.objects.filter(username=target_username).first()

if not user:
    log(f"CRITICAL: User '{target_username}' not found in database!")
else:
    log(f"User '{user.username}' (ID: {user.id}) identified.")

    # 2. Check the Queue
    templates = Item.objects.filter(user=user, is_recurring=True)
    log(f"Master Queue: Found {templates.count()} templates for this user.")
    
    for t in templates:
        log(f"  - Template: {t.description} | Price: {t.unit_price} | Client: {t.client}")

    if templates.count() == 0:
        log("ABORTING: No templates found.")
    else:
        # 3. Execute Service
        log("Calling import_recurring_to_invoices...")
        try:
            created_pks = import_recurring_to_invoices(user)
            log(f"SUCCESS: Service returned {len(created_pks)} invoice IDs.")
            
            # 4. Verification Loop
            for pk in created_pks:
                inv = Invoice.objects.get(pk=pk)
                log(f"VERIFICATION: Invoice #{inv.number} generated for {inv.client.name}")
                log(f"              Total Amount: R {inv.total_amount}")
                log(f"              Items attached: {inv.items.count() if hasattr(inv, 'items') else 'Check billed_items'}")
                
        except Exception as e:
            import traceback
            log(f"CRASH IN SERVICE: {str(e)}")
            log(traceback.format_exc())

log("Test script finished execution.")
