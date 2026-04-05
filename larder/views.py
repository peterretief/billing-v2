from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.urls import reverse_lazy
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import (
    LarderItem, GroceryStore, ProductMaster, ProductPrice,
    Recipe, Menu, MealPlan, ShoppingList, Ingredient, Criteria, Order
)
from .serializers import LarderItemSerializer

from .services import get_or_create_global_product

class OpenFoodFactsLookupView(View):
    """
    A simple UI view to enter a barcode and check OpenFoodFacts.
    """
    def get(self, request):
        return render(request, 'larder/off_lookup.html')

    def post(self, request):
        barcode = request.POST.get('barcode', '').strip()
        product = None
        error = None
        is_new = False

        if barcode:
            product, is_new = get_or_create_global_product(barcode)
            if not product:
                error = f"Product with barcode {barcode} not found in OpenFoodFacts or local database."
        else:
            error = "Please enter a barcode."

        return render(request, 'larder/off_lookup.html', {
            'product': product,
            'is_new': is_new,
            'error': error,
            'barcode': barcode,
            'quality_score': product.quality_score if product else 0
        })

class ProductPriceComparisonView(View):
    """
    View to compare prices for a specific product across stores.
    """
    def get(self, request, pk):
        product = get_object_or_404(ProductMaster, pk=pk)
        prices = product.prices.all().order_by('price')
        stores = GroceryStore.objects.all()
        
        return render(request, 'larder/price_comparison.html', {
            'product': product,
            'prices': prices,
            'stores': stores
        })

    def post(self, request, pk):
        product = get_object_or_404(ProductMaster, pk=pk)
        store_id = request.POST.get('store')
        price = request.POST.get('price')
        unit_size = request.POST.get('unit_size')
        unit_type = request.POST.get('unit_type')
        
        if store_id and price and unit_size:
            store = get_object_or_404(GroceryStore, pk=store_id)
            ProductPrice.objects.update_or_create(
                product=product,
                store=store,
                defaults={
                    'price': price,
                    'unit_size': unit_size,
                    'unit_type': unit_type,
                    'is_on_sale': 'is_on_sale' in request.POST
                }
            )
            messages.success(request, f"Price updated for {product.name} at {store.name}")
        
        return redirect('larder:price-comparison', pk=pk)

class ProductMasterListView(View):
    """
    List all products in the master registry.
    """
    def get(self, request):
        products = ProductMaster.objects.all().order_by('name')
        return render(request, 'larder/product_list.html', {'products': products})

# --- Meal Planning Views ---

class RecipeListView(ListView):
    """List all recipes for the user."""
    model = Recipe
    template_name = 'larder/recipe_list.html'
    context_object_name = 'recipes'
    ordering = ['name']

class MenuListView(ListView):
    """List all menus for the user."""
    model = Menu
    template_name = 'larder/menu_list.html'
    context_object_name = 'menus'
    ordering = ['meal_period', 'name']

class MealPlanListView(ListView):
    """List all meal plans for the user."""
    model = MealPlan
    template_name = 'larder/mealplan_list.html'
    context_object_name = 'meal_plans'
    ordering = ['-start_date']

class ShoppingListView(ListView):
    """List all shopping lists for the user."""
    model = ShoppingList
    template_name = 'larder/shoppinglist_list.html'
    context_object_name = 'shopping_lists'
    ordering = ['-created_at']

# --- Existing Views ---

# This is the missing piece!
class LarderItemViewSet(viewsets.ModelViewSet):
    """
    Handles viewing, updating, and deleting items in the larder.
    """
    serializer_class = LarderItemSerializer

    def get_queryset(self):
        # Because we use TenantModel, we want to make sure we 
        # only show items for the current tenant.
        # This assumes your TenantModel/Middleware handles the filtering,
        # but calling .all() is the standard starting point.
        return LarderItem.objects.filter(is_consumed=False)

# This is your existing scan logic
class BarcodeScanView(APIView):
    def post(self, request):
        barcode = request.data.get('barcode')
        product, is_new = get_or_create_global_product(barcode)

        if not product:
            return Response({"status": "not_found", "barcode": barcode})

        # Logic to add to larder...
        # (The rest of your scan code goes here)
        return Response({"status": "success", "name": product.name})