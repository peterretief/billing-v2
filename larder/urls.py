from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LarderItemViewSet, BarcodeScanView, OpenFoodFactsLookupView, 
    ProductMasterListView,
    RecipeListView, RecipeDetailView, RecipeCreateView, RecipeUpdateView, RecipeDeleteView,
    MenuListView, MenuDetailView, MenuCreateView, MenuUpdateView,
    MealPlanListView, MealPlanDetailView, MealPlanCreateView, MealPlanUpdateView,
    MealPlanDayUpdateView,
    ShoppingListView, ShoppingListDetailView,
    OrderListView, OrderDetailView, OrderCreateView, OrderUpdateView,
    RecipeViewSet, MenuViewSet, MealPlanViewSet, MealPlanDayViewSet,
    ShoppingListViewSet, OrderViewSet
)

# Router handles the standard CRUD for your larder
router = DefaultRouter()
router.register(r'inventory', LarderItemViewSet, basename='larder-inventory')
router.register(r'recipes', RecipeViewSet, basename='recipe-api')
router.register(r'menus', MenuViewSet, basename='menu-api')
router.register(r'meal-plans', MealPlanViewSet, basename='mealplan-api')
router.register(r'meal-plan-days', MealPlanDayViewSet, basename='mealplanday-api')
router.register(r'shopping-lists', ShoppingListViewSet, basename='shoppinglist-api')
router.register(r'orders', OrderViewSet, basename='order-api')

app_name = 'larder'

urlpatterns = [
    # Recipe URLs
    path('recipes/', RecipeListView.as_view(), name='recipe-list'),
    path('recipes/create/', RecipeCreateView.as_view(), name='recipe-create'),
    path('recipes/<int:pk>/', RecipeDetailView.as_view(), name='recipe-detail'),
    path('recipes/<int:pk>/edit/', RecipeUpdateView.as_view(), name='recipe-update'),
    path('recipes/<int:pk>/delete/', RecipeDeleteView.as_view(), name='recipe-delete'),
    
    # Menu URLs
    path('menus/', MenuListView.as_view(), name='menu-list'),
    path('menus/create/', MenuCreateView.as_view(), name='menu-create'),
    path('menus/<int:pk>/', MenuDetailView.as_view(), name='menu-detail'),
    path('menus/<int:pk>/edit/', MenuUpdateView.as_view(), name='menu-update'),
    
    # MealPlan URLs
    path('meal-plans/', MealPlanListView.as_view(), name='mealplan-list'),
    path('meal-plans/create/', MealPlanCreateView.as_view(), name='mealplan-create'),
    path('meal-plans/<int:pk>/', MealPlanDetailView.as_view(), name='mealplan-detail'),
    path('meal-plans/<int:pk>/edit/', MealPlanUpdateView.as_view(), name='mealplan-update'),
    path('meal-plan-days/<int:pk>/edit/', MealPlanDayUpdateView.as_view(), name='mealplanday-update'),
    
    # Shopping List URLs
    path('shopping-lists/', ShoppingListView.as_view(), name='shoppinglist-list'),
    path('shopping-lists/<int:pk>/', ShoppingListDetailView.as_view(), name='shoppinglist-detail'),
    
    # Order URLs
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('orders/create/', OrderCreateView.as_view(), name='order-create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/edit/', OrderUpdateView.as_view(), name='order-update'),

    # Product Master Views
    path('products/', ProductMasterListView.as_view(), name='product-list'),
    
    # OpenFoodFacts Lookup
    path('off-lookup/', OpenFoodFactsLookupView.as_view(), name='off-lookup'),

    # API Routes
    path('api/', include(router.urls)),
    path('api/scan/', BarcodeScanView.as_view(), name='barcode-scan'),
]