from rest_framework import serializers
from .models import (
    ProductMaster, LarderItem, GroceryStore,
    Recipe, Ingredient, Criteria, Menu, MealPlan, MealPlanDay,
    ShoppingList, Order, MenuRecipe
)

class ProductMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMaster
        fields = ['id', 'barcode', 'name', 'brand', 'nutrition_data', 'metadata']

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
        fields = ['id', 'product', 'store', 'quantity', 'unit', 'price_paid', 'expiry_date', 'is_consumed']


# Meal Planning Serializers

class IngredientSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = Ingredient
        fields = ['id', 'product', 'product_name', 'quantity', 'unit']


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = IngredientSerializer(many=True, read_only=True)
    total_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Recipe
        fields = [
            'id', 'name', 'description', 'ingredients', 'calories',
            'protein_g', 'carbs_g', 'fat_g', 'is_vegetarian', 'is_vegan',
            'allergens', 'prep_time_minutes', 'cook_time_minutes', 'total_time',
            'created_at', 'updated_at'
        ]
    
    def get_total_time(self, obj):
        """Get total prep + cook time."""
        return obj.total_time_minutes()


class CriteriaSerializer(serializers.ModelSerializer):
    matching_recipes_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Criteria
        fields = ['id', 'name', 'max_calories', 'vegetarian', 'vegan', 'exclude_allergens', 'matching_recipes_count']
    
    def get_matching_recipes_count(self, obj):
        """Count recipes matching this criteria."""
        return len(obj.get_matching_recipes())


class MenuRecipeSerializer(serializers.ModelSerializer):
    recipe = RecipeSerializer(read_only=True)
    
    class Meta:
        model = MenuRecipe
        fields = ['id', 'recipe', 'order']


class MenuSerializer(serializers.ModelSerializer):
    recipes = serializers.PrimaryKeyRelatedField(many=True, queryset=Recipe.objects.all())
    recipe_details = MenuRecipeSerializer(source='menurecipe_set', many=True, read_only=True)
    
    class Meta:
        model = Menu
        fields = ['id', 'name', 'meal_period', 'recipes', 'recipe_details', 'criteria']


class MealPlanDaySerializer(serializers.ModelSerializer):
    meals = MenuSerializer(source='menus', many=True, read_only=True)
    day_of_week = serializers.SerializerMethodField()
    
    class Meta:
        model = MealPlanDay
        fields = ['id', 'day_date', 'day_of_week', 'meals']
    
    def get_day_of_week(self, obj):
        """Get day name (Monday, Tuesday, etc)."""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[obj.day_date.weekday()]


class MealPlanSerializer(serializers.ModelSerializer):
    meal_plan_days = MealPlanDaySerializer(many=True, read_only=True)
    ingredients = serializers.SerializerMethodField()
    days_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MealPlan
        fields = [
            'id', 'name', 'time_period', 'start_date', 'end_date',
            'criteria', 'meal_plan_days', 'ingredients', 'days_count', 'created_at'
        ]
    
    def get_ingredients(self, obj):
        """Get all ingredients needed."""
        ingredients = obj.get_all_ingredients()
        return ProductMasterSerializer(ingredients, many=True).data
    
    def get_days_count(self, obj):
        """Get number of days."""
        return obj.get_days_count()


class ShoppingListItemSerializer(serializers.Serializer):
    """Serializer for shopping list items (auto-generated)."""
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    total_quantity = serializers.FloatField()
    unit = serializers.CharField()


class ShoppingListSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ShoppingList
        fields = [
            'id', 'name', 'meal_plan', 'is_purchased', 'purchased_at',
            'total_cost', 'items', 'items_count', 'created_at', 'updated_at'
        ]
    
    def get_items(self, obj):
        """Get aggregated shopping items."""
        items = obj.get_items()
        serializer = ShoppingListItemSerializer(
            [{'product_id': item['product'].id, 'product_name': item['product'].name,
              'total_quantity': item['total_quantity'], 'unit': item['unit']}
             for item in items],
            many=True
        )
        return serializer.data
    
    def get_items_count(self, obj):
        """Get count of items."""
        return len(obj.get_items())


class OrderSerializer(serializers.ModelSerializer):
    shopping_list_name = serializers.CharField(source='shopping_list.name', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'shopping_list', 'shopping_list_name', 'status', 'store',
            'store_name', 'total_amount', 'ordered_at', 'delivered_at', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'ordered_at', 'delivered_at']
        fields = [
            'id', 'product', 'store', 'quantity', 
            'unit', 'price_paid', 'expiry_date', 'is_consumed'
        ]