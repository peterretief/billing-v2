import datetime
import re
import uuid
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Invoice


from django.db.models.signals import post_save, post_delete
from .models import Invoice, InvoiceItem

@receiver(post_save, sender=InvoiceItem)
@receiver(post_delete, sender=InvoiceItem)
def update_invoice_totals_on_item_change(sender, instance, **kwargs):
    """
    Automatically recalculate invoice totals whenever a line item 
    is created, updated, or deleted.
    """
    invoice = instance.invoice
    # Call your manager logic
    Invoice.objects.update_totals(invoice)

@receiver(post_save, sender=Invoice)
def update_totals_on_tax_mode_change(sender, instance, created, **kwargs):
    """
    If the Tax Setting (tax_mode) is changed on the Invoice header,
    we need to recalculate even if the items didn't change.
    """
    # Prevent infinite recursion by checking if update_fields was used
    if kwargs.get('update_fields') and 'total_amount' in kwargs.get('update_fields'):
        return
        
    Invoice.objects.update_totals(instance)


@receiver(pre_save, sender=Invoice)
def create_invoice_number(sender, instance, **kwargs):
    # Only generate if number is missing or empty
    if not instance.number:
        try:
            # Use provided date or fallback to today
            today = instance.date_issued or datetime.date.today()
            short_year = today.strftime("%y")
            
            # Ensure we have a client code
            client_code = "INV"
            if instance.client and hasattr(instance.client, 'client_code'):
                client_code = instance.client.client_code or "INV"
            
            # 1. Sequential Logic: Filter by User + Client + Current Year
            last_invoice = Invoice.objects.filter(
                user=instance.user,
                client=instance.client,
                number__icontains=f"-{short_year}"
            ).order_by('id').last() # Order by ID to get the literal last entry

            if last_invoice:
                # Regex looks for: CLIENT-NUMBER-YEAR
                # Example: ACME-05-26
                pattern = rf'{re.escape(client_code)}-(\d+)-{short_year}'
                match = re.search(pattern, last_invoice.number)
                
                if match:
                    next_sequence = int(match.group(1)) + 1
                else:
                    # If pattern is weird, count total invoices for this client/year
                    next_sequence = Invoice.objects.filter(
                        user=instance.user, 
                        client=instance.client,
                        number__icontains=f"-{short_year}"
                    ).count() + 1
            else:
                next_sequence = 1
            
            # Construct the target number
            new_number = f"{client_code}-{next_sequence:02d}-{short_year}"

            # FINAL SAFETY CHECK: If this number ALREADY exists for this user, 
            # increment until it doesn't to avoid IntegrityError.
            while Invoice.objects.filter(user=instance.user, number=new_number).exists():
                next_sequence += 1
                new_number = f"{client_code}-{next_sequence:02d}-{short_year}"
            
            instance.number = new_number

        except Exception as e:
            # 2. FALLBACK: Create a unique random string if the above fails
            # This ensures the save NEVER fails due to a numbering error
            today_str = datetime.date.today().strftime("%Y")
            random_suffix = uuid.uuid4().hex[:4].upper()
            client_prefix = instance.client.client_code if (instance.client and instance.client.client_code) else "INV"
            
            instance.number = f"{client_prefix}-{today_str}-{random_suffix}"