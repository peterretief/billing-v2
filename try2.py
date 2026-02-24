import sys

from django.contrib.auth import get_user_model

from items.models import Item
from items.services import import_recurring_to_invoices


def log(msg):
    print(f">>> [DEBUG] {msg}")
    sys.stdout.flush()


log("Starting the Item-driven Billing Test...")

# 1. Fetch User
User = get_user_model()
target_username = "peter"
user = User.objects.filter(username=target_username).first()

if not user:
    log(f"CRITICAL: User '{target_username}' not found in database!")
else:
    log(f"User '{user.username}' (ID: {user.id}) identified.")

    # 2. Check the Queue
    templates = Item.objects.filter(user=user, is_recurring=True)
    log(f"Master Queue: Found {templates.count()} templates for this user.")

    for t in templates:
        log(f"  - Found Template: {t.description} (Client: {t.client})")

    if templates.count() == 0:
        log("ABORTING: No templates found. Ensure 'is_recurring' is checked in the Bottom Table.")
    else:
        # 3. Execute Service
        log("Calling import_recurring_to_invoices...")
        try:
            result = import_recurring_to_invoices(user)
            log(f"SERVICE RESULT: {result}")
        except Exception as e:
            log(f"CRASH IN SERVICE: {str(e)}")

log("Test script finished execution.")
