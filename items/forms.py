# items/forms.py
from django import forms
from .models import Item

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['client', 'description', 'quantity', 'unit_price', 'date']
