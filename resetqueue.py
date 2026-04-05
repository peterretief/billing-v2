# Quick reset in Django shell
from items.models import Item
Item.objects.filter(is_recurring=True).update(last_billed_date=None, invoice=None, is_billed=False)
