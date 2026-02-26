# items/forms.py
from django import forms

from billing_schedule.models import BillingPolicy

# items/forms.py
from .models import Item, ServiceItem


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            "client",
            "description",
            "quantity",
            "unit_price",
            "date",
            "is_taxable",
            "is_recurring",
            "billing_policy",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "billing_policy": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        # 1. Pop the user out of the kwargs (passed from the view)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # 2. Filter the Querysets by the logged-in user
        if user:
            # Only show this user's clients
            self.fields["client"].queryset = self.fields["client"].queryset.filter(user=user)

            # Only show this user's billing policies
            self.fields["billing_policy"].queryset = BillingPolicy.objects.filter(user=user)

            # Make the dropdown more readable in the form
            self.fields["billing_policy"].empty_label = "Select a schedule (Optional)"

        # Disable client field if item is already linked to an invoice
        if self.instance and self.instance.pk and self.instance.invoice_id:
            self.fields["client"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        
        # Prevent changing client if item is already in an invoice (business rule from ItemManager)
        if self.instance and self.instance.pk and self.instance.invoice_id:
            if cleaned_data.get("client") != self.instance.client:
                raise forms.ValidationError(
                    "Cannot change the client for items that are already linked to an invoice. "
                    "The item must stay with its original client."
                )
        
        return cleaned_data


class ServiceItemForm(forms.ModelForm):
    class Meta:
        model = ServiceItem
        fields = ["description", "price", "billing_policy", "is_recurring"]

    def __init__(self, *args, **kwargs):
        # We need to pass the user into the form from the view
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user:
            # Filter the dropdown to only show THIS user's policies
            self.fields["billing_policy"].queryset = BillingPolicy.objects.filter(user=user)
