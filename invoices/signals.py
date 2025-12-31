import datetime
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Invoice


@receiver(pre_save, sender=Invoice)
def create_invoice_number(sender, instance, **kwargs):
    # We only generate a number if it doesn't have one yet (new invoice)
    if not instance.pk or not instance.number:
        today = datetime.date.today()
        short_year = today.strftime("%y")
        
        # Get the count of invoices for THIS user and THIS client this year
        count = Invoice.objects.filter(
            user=instance.user,
            client=instance.client,
            date_issued__year=today.year
        ).count()

        next_sequence = count + 1
        
        # Pull the client_code we generated in the Client model
        client_code = instance.client.client_code
        
        # Final Format: ACME-01-25
        instance.number = f"{client_code}-{next_sequence:02d}-{short_year}"        