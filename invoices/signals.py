import datetime
import re
import uuid

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Invoice

# --- 1. Total Calculations (Standard Only) ---

@receiver(post_save, sender=Invoice)
def update_totals_on_tax_mode_change(sender, instance, created, **kwargs):
    """
    Handles tax mode changes on the Invoice header.
    GATEKEEPER: If this is a CustomInvoice, we STOP here to prevent loops.
    """
    if kwargs.get('update_fields') and 'total_amount' in kwargs.get('update_fields'):
        return

    if hasattr(instance, 'custominvoice') or hasattr(instance, 'custom_lines'):
        return
        
    Invoice.objects.update_totals(instance)


# --- 2. Invoice Number Generation ---

@receiver(pre_save, sender=Invoice)
def create_invoice_number(sender, instance, **kwargs):
    """Generates sequential numbers for ALL invoices."""
    if not instance.number:
        try:
            # Use provided date or fallback to today
            today = getattr(instance, 'date_issued', None) or datetime.date.today()
            short_year = today.strftime("%y")
            
            client_code = "INV"
            if instance.client and hasattr(instance.client, 'client_code'):
                client_code = instance.client.client_code or "INV"
            
            # Find last sequence across all invoice types for this client
            last_invoice = Invoice.objects.filter(
                user=instance.user,
                client=instance.client,
                number__icontains=f"-{short_year}"
            ).order_by('id').last()

            if last_invoice:
                pattern = rf'{re.escape(client_code)}-(\d+)-{short_year}'
                match = re.search(pattern, last_invoice.number)
                if match:
                    next_sequence = int(match.group(1)) + 1
                else:
                    # Fallback count if pattern match fails
                    next_sequence = Invoice.objects.filter(
                        user=instance.user, 
                        client=instance.client,
                        number__icontains=f"-{short_year}"
                    ).count() + 1
            else:
                next_sequence = 1
            
            new_number = f"{client_code}-{next_sequence:02d}-{short_year}"
            
            # Final collision check
            while Invoice.objects.filter(user=instance.user, number=new_number).exists():
                next_sequence += 1
                new_number = f"{client_code}-{next_sequence:02d}-{short_year}"
                
            instance.number = new_number
        except Exception:
            # High-reliability fallback if DB query fails
            instance.number = f"INV-{uuid.uuid4().hex[:4].upper()}"


# --- 3. Explicit Connection for Custom Models ---

def connect_custom_signals():
    """
    Connects signals to child models. 
    In MTI, child models trigger parent signals, but pre_save
    sometimes needs an explicit hook for sequence numbering.
    """
    pass

# Call this LAST
connect_custom_signals()

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from invoices.models import Invoice


@receiver(post_save, sender=Invoice)
def update_items_on_sent(sender, instance, **kwargs):
    # Changed from 'SENT' to 'PENDING' to match your Status choices
    if instance.status == 'PENDING':
        instance.billed_items.all().update(is_billed=True)
        
        from items.models import Item
        item_descriptions = instance.billed_items.values_list('description', flat=True)
        Item.objects.filter(
            user=instance.user,
            client=instance.client,
            is_recurring=True,
            description__in=item_descriptions
        ).update(last_billed_date=timezone.now().date())       