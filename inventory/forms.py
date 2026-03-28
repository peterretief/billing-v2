from django import forms
from .models import Warehouse, InventoryItem, StockTransaction

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'location', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['sku', 'name', 'description', 'unit_of_measure', 'reorder_level', 'current_stock', 'buy_price', 'sell_price']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit_of_measure': forms.TextInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'buy_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sell_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['inventory_item', 'warehouse', 'transaction_type', 'quantity', 'reference', 'notes']
        widgets = {
            'inventory_item': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['inventory_item'].queryset = InventoryItem.objects.filter(user=user)
            self.fields['warehouse'].queryset = Warehouse.objects.filter(user=user)
