from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LarderItemViewSet, BarcodeScanView, OpenFoodFactsLookupView, 
    ProductMasterListView,
    RecipeListView, MenuListView, MealPlanListView, ShoppingListView
)

# Router handles the standard CRUD for your larder
router = DefaultRouter()
router.register(r'inventory', LarderItemViewSet, basename='larder-inventory')

app_name = 'larder'

urlpatterns = [
    # Meal Planning Views
    path('recipes/', RecipeListView.as_view(), name='recipe-list'),
    path('menus/', MenuListView.as_view(), name='menu-list'),
    path('meal-plans/', MealPlanListView.as_view(), name='mealplan-list'),
    path('shopping-lists/', ShoppingListView.as_view(), name='shoppinglist-list'),

    # Product Master Views
    path('products/', ProductMasterListView.as_view(), name='product-list'),
    
    # OpenFoodFacts Lookup
    path('off-lookup/', OpenFoodFactsLookupView.as_view(), name='off-lookup'),

    # API Routes
    path('api/', include(router.urls)),
    path('api/scan/', BarcodeScanView.as_view(), name='barcode-scan'),
]