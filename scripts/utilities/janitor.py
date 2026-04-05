# janitor.py
from items.models import Item


def run():
    print("--- Starting Item Database Cleanup ---")

    # The 'is_billed' flag has been removed from the Item model.
    # An item is now considered 'billed' if it has a non-null 'invoice' foreign key.
    
    # Check for recurring items that aren't linked to an invoice yet.
    pending = Item.objects.filter(invoice__isnull=True)
    print(f"Found {pending.count()} items currently waiting for an invoice.")

    print("--- Cleanup Finished ---")


if __name__ == "__main__":
    run()
