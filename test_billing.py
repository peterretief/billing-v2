# /opt/billing_v2/test_billing.py
from datetime import date

from django.db import IntegrityError

from invoices.models import Invoice
from invoices.tasks import generate_recurring_monthly_invoices


if __name__ == "__main__":
    print("--- Starting Billing Test Script ---")

    # 1. Test the actual Task logic (with the workday check)
    print("Testing scheduled task logic...")
    result = generate_recurring_monthly_invoices()
    print(f"Task Result: {result}")

    # 2. Force a clone for testing (ignoring the workday check)
    print("\nForcing a template clone for verification...")
    templates = Invoice.objects.filter(is_template=True)

    if not templates.exists():
        print("Error: No templates found! Check 'is_template' in Admin.")
    else:
        for template in templates:
            try:
                # Create the clone
                new_inv = Invoice.objects.get(pk=template.pk)
                new_inv.pk = None
                new_inv.date_issued = date.today()
                new_inv.is_template = False
                new_inv.status = "DRAFT"

                # Use a unique test number to avoid IntegrityErrors
                timestamp = date.today().strftime("%y%m%d")
                new_inv.number = f"T-{timestamp}-{template.client.id}"

                new_inv.save()

                # Clone items
                from items.models import Item

                for item_to_clone in template.billed_items.all():
                    Item.objects.create(
                        user=template.user,
                        client=template.client,
                        invoice=new_inv,
                        description=item_to_clone.description,
                        quantity=item_to_clone.quantity,
                        unit_price=item_to_clone.unit_price,
                        is_taxable=item_to_clone.is_taxable,
                        is_recurring=item_to_clone.is_recurring,
                    )
                new_inv.sync_totals()
                new_inv.save()

                print(f"Successfully created: {new_inv.number}")

            except IntegrityError:
                print(f"Skipping {template.client}: Duplicate number detected.")
            except Exception as e:
                print(f"Unexpected error: {e}")

    print("\n--- Test Complete ---")
