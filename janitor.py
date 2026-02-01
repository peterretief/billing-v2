# janitor.py
from items.models import Item


def run():
    print("--- Starting Item Database Cleanup ---")
    
    # Check for items that are linked to an invoice but the 'is_billed' flag didn't flip
    # (Common if the PDF generation crashed mid-task)
    orphans = Item.objects.filter(invoice__isnull=False, is_billed=False)
    
    if not orphans.exists():
        print("No orphaned items found.")
    else:
        for item in orphans:
            print(f"Fixing Item {item.id}: Marking as billed (Linked to Invoice {item.invoice.number})")
            item.is_billed = True
            item.save()

    # Check for recurring items that might have 'doubled' in the queue
    # but aren't linked to an invoice yet.
    pending = Item.objects.filter(invoice__isnull=True, is_billed=False)
    print(f"Found {pending.count()} items currently waiting for an invoice.")

    print("--- Cleanup Finished ---")

if __name__ == "__main__":
    run()
