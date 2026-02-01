# items/forms.py
from django import forms

from .models import Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['client', 'description', 'quantity', 'unit_price', 'date', 'is_recurring', 'is_taxable']
        widgets = {
            'is_taxable': forms.HiddenInput(), # Keeps it in the form but invisible
        }