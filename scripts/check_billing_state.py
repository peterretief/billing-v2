from billing_schedule.models import BillingPolicy
from items.models import Item
from django.utils import timezone

today = timezone.now().date()
print(f"Current Date: {today}")

policies = BillingPolicy.objects.all()
print("\n--- Billing Policies ---")
for p in policies:
    print(f"ID: {p.id}, Name: {p.name}, Day: {p.run_day}, Rule: {p.special_rule}, Active: {p.is_active}")

recurring_items = Item.objects.filter(is_recurring=True)
print("\n--- Recurring Items ---")
for item in recurring_items:
    policy_name = item.billing_policy.name if item.billing_policy else "Master Queue"
    invoice_num = item.invoice.number if item.invoice else "None"
    print(f"Item: {item.description}, Client: {item.client.name}, Policy: {policy_name}, Last Billed: {item.last_billed_date}, Invoice: {invoice_num}")

due_policies = BillingPolicy.objects.due_today()
print("\n--- Due Today Policies ---")
for p in due_policies:
    print(f"ID: {p.id}, Name: {p.name}")
