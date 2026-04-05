from rest_framework import serializers
from .models import ProductMaster, LarderItem, GroceryStore

class ProductMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMaster
        fields = ['barcode', 'name', 'brand', 'nutrition_data', 'metadata']

class GroceryStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroceryStore
        fields = ['id', 'name']

class LarderItemSerializer(serializers.ModelSerializer):
    # This nests the product info so you see "Milk" instead of just a Product ID
    product = ProductMasterSerializer(read_only=True)
    store = GroceryStoreSerializer(read_only=True)

    class Meta:
        model = LarderItem
        fields = [
            'id', 'product', 'store', 'quantity', 
            'unit', 'price_paid', 'expiry_date', 'is_consumed'
        ]