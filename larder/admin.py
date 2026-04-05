from django.contrib import admin
from .models import (
    GroceryStore, ProductMaster, ProductPrice, LarderItem,
    Recipe, Ingredient, Criteria, Menu, MenuRecipe,
    MealPlan, MealPlanDay, ShoppingList, ShoppingListItem, Order
)

@admin.register(GroceryStore)
class GroceryStoreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ProductMaster)
class ProductMasterAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'brand')
    search_fields = ('barcode', 'name', 'brand')
    readonly_fields = ('nutrition_data', 'metadata')

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'store', 'price', 'unit_size', 'unit_type', 'last_updated')
    list_filter = ('store', 'is_on_sale', 'last_updated')
    search_fields = ('product__name', 'store__name')

@admin.register(LarderItem)
class LarderItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'expiry_date', 'is_consumed')
    list_filter = ('expiry_date', 'is_consumed', 'user')
    search_fields = ('product__name', 'user__username')

# Meal Planning Admin

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'quantity', 'unit')
    list_filter = ('unit', 'user')
    search_fields = ('product__name', 'user__username')

@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_vegetarian', 'is_vegan', 'calories')
    list_filter = ('is_vegetarian', 'is_vegan', 'user')
    search_fields = ('name', 'user__username')
    filter_horizontal = ('ingredients',)

@admin.register(Criteria)
class CriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'max_calories', 'vegetarian', 'vegan')
    list_filter = ('vegetarian', 'vegan', 'user')
    search_fields = ('name', 'user__username')

@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'meal_period')
    list_filter = ('meal_period', 'user')
    search_fields = ('name', 'user__username')

@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'time_period', 'start_date', 'end_date')
    list_filter = ('time_period', 'user', 'start_date')
    search_fields = ('name', 'user__username')
    date_hierarchy = 'start_date'

@admin.register(MealPlanDay)
class MealPlanDayAdmin(admin.ModelAdmin):
    list_display = ('meal_plan', 'day_date')
    list_filter = ('day_date', 'meal_plan__user')
    search_fields = ('meal_plan__name',)
    filter_horizontal = ('menus',)

class ShoppingListItemInline(admin.TabularInline):
    model = ShoppingListItem
    extra = 0
    fields = ('product', 'quantity', 'unit', 'estimated_cost', 'purchased')
    readonly_fields = ('created_at',)

@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'meal_plan', 'is_purchased', 'total_cost')
    list_filter = ('is_purchased', 'user', 'created_at')
    search_fields = ('name', 'user__username', 'meal_plan__name')
    inlines = [ShoppingListItemInline]

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'shopping_list', 'status', 'store', 'total_amount', 'ordered_at')
    list_filter = ('status', 'user', 'ordered_at', 'store')
    search_fields = ('user__username', 'shopping_list__name', 'notes')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ShoppingListItem)
class ShoppingListItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'shopping_list', 'quantity', 'unit', 'estimated_cost', 'purchased')
    list_filter = ('purchased', 'unit', 'shopping_list__user')
    search_fields = ('product__name', 'shopping_list__name')
    readonly_fields = ('created_at', 'updated_at')