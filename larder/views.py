from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.filters import SearchFilter
from .models import (
    LarderItem, GroceryStore, ProductMaster, ProductPrice,
    Recipe, Menu, MealPlan, ShoppingList, Ingredient, Criteria, Order, MealPlanDay, ShoppingListItem
)
from .serializers import (
    LarderItemSerializer, ProductMasterSerializer, GroceryStoreSerializer,
    RecipeSerializer, IngredientSerializer, CriteriaSerializer,
    MenuSerializer, MealPlanSerializer, MealPlanDaySerializer,
    ShoppingListSerializer, OrderSerializer
)
from .forms import (
    RecipeForm, IngredientForm, CriteriaForm, MenuForm, MealPlanForm,
    MealPlanDayForm, ShoppingListForm, OrderForm, MealPlanQuickCreateForm,
    BulkMenuAssignmentForm
)
from .services import get_or_create_global_product
from .meal_planning_service import (
    MealPlanGenerator, MealPlanOptimizer, quick_generate_meal_plan,
    auto_create_shopping_list, bulk_assign_menus_to_days, suggest_recipes_for_menu
)

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
    paginate_by = 20
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user).order_by('name')


class RecipeDetailView(LoginRequiredMixin, DetailView):
    """View recipe details."""
    model = Recipe
    template_name = 'larder/recipe_detail.html'
    context_object_name = 'recipe'
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeCreateView(LoginRequiredMixin, CreateView):
    """Create a new recipe."""
    model = Recipe
    form_class = RecipeForm
    template_name = 'larder/recipe_form.html'
    success_url = reverse_lazy('larder:recipe-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        # Ingredients are saved by form.save() method
        messages.success(self.request, f"Recipe '{form.instance.name}' created successfully!")
        return response
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ingredients'] = Ingredient.objects.filter(user=self.request.user).select_related('product')
        return context


class RecipeUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a recipe."""
    model = Recipe
    form_class = RecipeForm
    template_name = 'larder/recipe_form.html'
    success_url = reverse_lazy('larder:recipe-list')
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, f"Recipe '{form.instance.name}' updated successfully!")
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ingredients'] = Ingredient.objects.filter(user=self.request.user).select_related('product')
        return context


class RecipeDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a recipe."""
    model = Recipe
    template_name = 'larder/recipe_confirm_delete.html'
    success_url = reverse_lazy('larder:recipe-list')
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.success(request, f"Recipe '{self.object.name}' deleted successfully!")
        return super().delete(request, *args, **kwargs)


class MenuListView(ListView):
    """List all menus for the user."""
    model = Menu
    template_name = 'larder/menu_list.html'
    context_object_name = 'menus'
    ordering = ['meal_period', 'name']
    
    def get_queryset(self):
        return Menu.objects.filter(user=self.request.user)


class MenuDetailView(LoginRequiredMixin, DetailView):
    """View menu details."""
    model = Menu
    template_name = 'larder/menu_detail.html'
    context_object_name = 'menu'
    
    def get_queryset(self):
        return Menu.objects.filter(user=self.request.user)


class MenuCreateView(LoginRequiredMixin, CreateView):
    """Create a new menu."""
    model = Menu
    form_class = MenuForm
    template_name = 'larder/menu_form.html'
    success_url = reverse_lazy('larder:menu-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Menu '{form.instance.name}' created!")
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class MenuUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a menu."""
    model = Menu
    form_class = MenuForm
    template_name = 'larder/menu_form.html'
    success_url = reverse_lazy('larder:menu-list')
    
    def get_queryset(self):
        return Menu.objects.filter(user=self.request.user)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class MealPlanListView(ListView):
    """List all meal plans for the user."""
    model = MealPlan
    template_name = 'larder/mealplan_list.html'
    context_object_name = 'meal_plans'
    ordering = ['-start_date']
    paginate_by = 15
    
    def get_queryset(self):
        return MealPlan.objects.filter(user=self.request.user)


class MealPlanDetailView(LoginRequiredMixin, DetailView):
    """View meal plan details with calendar."""
    model = MealPlan
    template_name = 'larder/mealplan_detail.html'
    context_object_name = 'meal_plan'
    
    def get_queryset(self):
        return MealPlan.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meal_plan = self.object
        context['meal_plan_days'] = meal_plan.meal_plan_days.all().order_by('day_date')
        context['ingredients'] = meal_plan.get_all_ingredients()
        context['total_days'] = meal_plan.get_days_count()
        return context


class MealPlanCreateView(LoginRequiredMixin, CreateView):
    """Create a new meal plan."""
    model = MealPlan
    form_class = MealPlanForm
    template_name = 'larder/mealplan_form.html'
    success_url = reverse_lazy('larder:mealplan-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        
        # Optionally auto-generate meal plan days
        if self.request.POST.get('auto_generate'):
            self.create_meal_plan_days(form.instance)
        
        messages.success(self.request, f"Meal plan '{form.instance.name}' created!")
        return response
    
    def create_meal_plan_days(self, meal_plan):
        """Auto-generate meal plan days."""
        from datetime import timedelta
        current_date = meal_plan.start_date
        while current_date <= meal_plan.end_date:
            MealPlanDay.objects.get_or_create(
                meal_plan=meal_plan,
                day_date=current_date
            )
            current_date += timedelta(days=1)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class MealPlanUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a meal plan."""
    model = MealPlan
    form_class = MealPlanForm
    template_name = 'larder/mealplan_form.html'
    success_url = reverse_lazy('larder:mealplan-list')
    
    def get_queryset(self):
        return MealPlan.objects.filter(user=self.request.user)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class MealPlanDayUpdateView(LoginRequiredMixin, UpdateView):
    """Update menus for a specific day in a meal plan."""
    model = MealPlanDay
    form_class = MealPlanDayForm
    template_name = 'larder/mealplanday_form.html'
    
    def get_queryset(self):
        return MealPlanDay.objects.filter(meal_plan__user=self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('larder:mealplan-detail', kwargs={'pk': self.object.meal_plan.pk})
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['meal_plan'] = self.object.meal_plan
        kwargs['user'] = self.request.user
        return kwargs


class ShoppingListView(ListView):
    """List all shopping lists for the user."""
    model = ShoppingList
    template_name = 'larder/shoppinglist_list.html'
    context_object_name = 'shopping_lists'
    ordering = ['-created_at']
    paginate_by = 20
    
    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user)


class ShoppingListDetailView(LoginRequiredMixin, DetailView):
    """View shopping list items with purchase tracking."""
    model = ShoppingList
    template_name = 'larder/shoppinglist_detail.html'
    context_object_name = 'shopping_list'
    
    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shopping_list = self.object
        context['items'] = shopping_list.get_items()
        context['item_count'] = len(context['items'])
        return context


class OrderListView(ListView):
    """List all orders for the user."""
    model = Order
    template_name = 'larder/order_list.html'
    context_object_name = 'orders'
    ordering = ['-created_at']
    paginate_by = 20
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderDetailView(LoginRequiredMixin, DetailView):
    """View order details."""
    model = Order
    template_name = 'larder/order_detail.html'
    context_object_name = 'order'
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderCreateView(LoginRequiredMixin, CreateView):
    """Create a new order from shopping list."""
    model = Order
    form_class = OrderForm
    template_name = 'larder/order_form.html'
    success_url = reverse_lazy('larder:order-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        
        # Get shopping list from URL parameters
        shopping_list_id = self.request.GET.get('shopping_list')
        if shopping_list_id:
            try:
                form.instance.shopping_list = ShoppingList.objects.get(
                    pk=shopping_list_id,
                    user=self.request.user
                )
            except ShoppingList.DoesNotExist:
                return HttpResponseForbidden("Invalid shopping list.")
        
        messages.success(self.request, "Order created!")
        return super().form_valid(form)


class OrderUpdateView(LoginRequiredMixin, UpdateView):
    """Update an order."""
    model = Order
    form_class = OrderForm
    template_name = 'larder/order_form.html'
    success_url = reverse_lazy('larder:order-list')
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, "Order updated!")
        return super().form_valid(form)


# --- Ingredient Management Views ---

class IngredientListView(LoginRequiredMixin, ListView):
    """List all ingredients."""
    model = Ingredient
    template_name = 'larder/ingredient_list.html'
    context_object_name = 'ingredients'
    paginate_by = 20
    
    def get_queryset(self):
        return Ingredient.objects.filter(user=self.request.user).select_related('product')


class IngredientCreateView(LoginRequiredMixin, CreateView):
    """Create a new ingredient."""
    model = Ingredient
    form_class = IngredientForm
    template_name = 'larder/ingredient_form.html'
    success_url = reverse_lazy('larder:ingredient-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        
        # Handle free-text ingredient name
        ingredient_name = form.cleaned_data.get('ingredient_name')
        if ingredient_name:
            # Auto-create ProductMaster for market produce
            product, _ = ProductMaster.objects.get_or_create(
                barcode=ingredient_name.lower().replace(' ', '_'),
                defaults={'name': ingredient_name}
            )
            form.instance.product = product
        
        messages.success(self.request, "Ingredient added!")
        return super().form_valid(form)


class IngredientUpdateView(LoginRequiredMixin, UpdateView):
    """Update an ingredient."""
    model = Ingredient
    form_class = IngredientForm
    template_name = 'larder/ingredient_form.html'
    success_url = reverse_lazy('larder:ingredient-list')
    
    def get_queryset(self):
        return Ingredient.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        # Handle free-text ingredient name
        ingredient_name = form.cleaned_data.get('ingredient_name')
        if ingredient_name:
            # Auto-create ProductMaster for market produce
            product, _ = ProductMaster.objects.get_or_create(
                barcode=ingredient_name.lower().replace(' ', '_'),
                defaults={'name': ingredient_name}
            )
            form.instance.product = product
        
        messages.success(self.request, "Ingredient updated!")
        return super().form_valid(form)


class IngredientDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an ingredient."""
    model = Ingredient
    template_name = 'larder/ingredient_confirm_delete.html'
    success_url = reverse_lazy('larder:ingredient-list')
    
    def get_queryset(self):
        return Ingredient.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Ingredient deleted!")
        return super().delete(request, *args, **kwargs)


# --- Dietary Criteria Views ---

class CriteriaListView(LoginRequiredMixin, ListView):
    """List all dietary criteria."""
    model = Criteria
    template_name = 'larder/criteria_list.html'
    context_object_name = 'criteria_list'
    paginate_by = 20
    
    def get_queryset(self):
        return Criteria.objects.filter(user=self.request.user).annotate(
            recipe_count=Count('menu__recipes', distinct=True)
        )


class CriteriaCreateView(LoginRequiredMixin, CreateView):
    """Create dietary criteria."""
    model = Criteria
    form_class = CriteriaForm
    template_name = 'larder/criteria_form.html'
    success_url = reverse_lazy('larder:criteria-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Dietary criteria created!")
        return super().form_valid(form)


class CriteriaUpdateView(LoginRequiredMixin, UpdateView):
    """Update dietary criteria."""
    model = Criteria
    form_class = CriteriaForm
    template_name = 'larder/criteria_form.html'
    success_url = reverse_lazy('larder:criteria-list')
    
    def get_queryset(self):
        return Criteria.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, "Criteria updated!")
        return super().form_valid(form)


class CriteriaDeleteView(LoginRequiredMixin, DeleteView):
    """Delete dietary criteria."""
    model = Criteria
    template_name = 'larder/criteria_confirm_delete.html'
    success_url = reverse_lazy('larder:criteria-list')
    
    def get_queryset(self):
        return Criteria.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Criteria deleted!")
        return super().delete(request, *args, **kwargs)


class CriteriaDetailView(LoginRequiredMixin, DetailView):
    """View criteria and matching recipes."""
    model = Criteria
    template_name = 'larder/criteria_detail.html'
    context_object_name = 'criteria'
    
    def get_queryset(self):
        return Criteria.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['matching_recipes'] = self.object.recipe_set.all()
        return context

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


# --- API ViewSets for Meal Planning ---

class RecipeViewSet(viewsets.ModelViewSet):
    """API ViewSet for Recipe CRUD operations."""
    serializer_class = RecipeSerializer
    permission_classes = []  # Customize as needed
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def by_criteria(self, request):
        """Get recipes matching specific criteria."""
        criteria_id = request.query_params.get('criteria_id')
        if not criteria_id:
            return Response({'error': 'criteria_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            criteria = Criteria.objects.get(pk=criteria_id, user=request.user)
            recipes = criteria.get_matching_recipes()
            serializer = RecipeSerializer(recipes, many=True)
            return Response(serializer.data)
        except Criteria.DoesNotExist:
            return Response({'error': 'Criteria not found'}, status=status.HTTP_404_NOT_FOUND)


class MenuViewSet(viewsets.ModelViewSet):
    """API ViewSet for Menu CRUD operations."""
    serializer_class = MenuSerializer
    permission_classes = []
    
    def get_queryset(self):
        return Menu.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['get'])
    def suggest_recipes(self, request, pk=None):
        """Get recipe suggestions for this menu's meal period."""
        menu = self.get_object()
        exclude_ids = request.query_params.getlist('exclude', [])
        
        recipes = suggest_recipes_for_menu(
            user=request.user,
            meal_period=menu.meal_period,
            criteria=menu.criteria,
            exclude_recipes=exclude_ids
        )
        
        serializer = RecipeSerializer(recipes, many=True)
        return Response(serializer.data)


class MealPlanViewSet(viewsets.ModelViewSet):
    """API ViewSet for MealPlan CRUD operations."""
    serializer_class = MealPlanSerializer
    permission_classes = []
    
    def get_queryset(self):
        return MealPlan.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def generate_quick(self, request):
        """Quick-generate a meal plan with auto-populated days and menus."""
        name = request.data.get('name')
        days = int(request.data.get('days', 7))
        criteria_id = request.data.get('criteria_id')
        
        if not name:
            return Response({'error': 'name required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            criteria = Criteria.objects.get(pk=criteria_id, user=request.user) if criteria_id else None
            meal_plan = quick_generate_meal_plan(
                user=request.user,
                name=name,
                days=days,
                criteria=criteria
            )
            serializer = MealPlanSerializer(meal_plan)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def generate_shopping_list(self, request, pk=None):
        """Generate shopping list from this meal plan."""
        meal_plan = self.get_object()
        
        try:
            shopping_list = auto_create_shopping_list(meal_plan)
            from .serializers import ShoppingListSerializer
            serializer = ShoppingListSerializer(shopping_list)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def suggest_balance(self, request, pk=None):
        """Get nutrition balance suggestions for this meal plan."""
        meal_plan = self.get_object()
        target_calories = int(request.data.get('target_calories', 2000))
        
        recommendations = MealPlanOptimizer.balance_nutrition(
            meal_plan,
            target_calories=target_calories
        )
        return Response({'recommendations': recommendations})
    
    @action(detail=True, methods=['post'])
    def check_variety(self, request, pk=None):
        """Check for recipe repetition in meal plan."""
        meal_plan = self.get_object()
        recommendations = MealPlanOptimizer.maximize_variety(meal_plan)
        return Response({'recommendations': recommendations})
    
    @action(detail=True, methods=['post'])
    def bulk_assign_menus(self, request, pk=None):
        """Bulk assign menus to multiple days."""
        meal_plan = self.get_object()
        menu_ids = request.data.get('menu_ids', [])
        day_type = request.data.get('day_type', 'all')  # 'all', 'weekdays', 'weekends'
        
        if not menu_ids:
            return Response({'error': 'menu_ids required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            menus = Menu.objects.filter(pk__in=menu_ids, user=request.user)
            if not menus.exists():
                return Response({'error': 'No valid menus found'}, status=status.HTTP_404_NOT_FOUND)
            
            bulk_assign_menus_to_days(meal_plan, list(menus), day_type)
            return Response({'status': 'success', 'message': f'Assigned {menus.count()} menus'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MealPlanDayViewSet(viewsets.ModelViewSet):
    """API ViewSet for MealPlanDay CRUD operations."""
    serializer_class = MealPlanDaySerializer
    permission_classes = []
    
    def get_queryset(self):
        return MealPlanDay.objects.filter(meal_plan__user=self.request.user)


class ShoppingListViewSet(viewsets.ModelViewSet):
    """API ViewSet for ShoppingList CRUD operations."""
    serializer_class = ShoppingListSerializer
    permission_classes = []
    
    def get_queryset(self):
        return ShoppingList.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def place_order(self, request, pk=None):
        """Create an order from this shopping list."""
        shopping_list = self.get_object()
        store_id = request.data.get('store_id')
        
        if not store_id:
            return Response({'error': 'store_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            store = GroceryStore.objects.get(pk=store_id)
            order = Order.objects.create(
                user=request.user,
                shopping_list=shopping_list,
                store=store,
                status='draft'
            )
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except GroceryStore.DoesNotExist:
            return Response({'error': 'Store not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def mark_purchased(self, request, pk=None):
        """Mark shopping list and all items as purchased."""
        shopping_list = self.get_object()
        
        # Mark all items as purchased
        shopping_list.shoppinglistitem_set.update(
            purchased=True,
            purchased_at=timezone.now()
        )
        
        # Mark shopping list as purchased
        shopping_list.is_purchased = True
        shopping_list.purchased_at = timezone.now()
        shopping_list.save()
        
        serializer = ShoppingListSerializer(shopping_list)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_item_purchased(self, request, pk=None):
        """Mark individual item as purchased."""
        shopping_list = self.get_object()
        item_id = request.data.get('item_id')
        
        if not item_id:
            return Response({'error': 'item_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            item = ShoppingListItem.objects.get(pk=item_id, shopping_list=shopping_list)
            item.mark_purchased()
            
            # Check if all items purchased
            if not shopping_list.shoppinglistitem_set.filter(purchased=False).exists():
                shopping_list.is_purchased = True
                shopping_list.purchased_at = timezone.now()
                shopping_list.save()
            
            return Response({'status': 'success', 'item_id': item.pk})
        except ShoppingListItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)


class OrderViewSet(viewsets.ModelViewSet):
    """API ViewSet for Order CRUD operations."""
    serializer_class = OrderSerializer
    permission_classes = []
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def place(self, request, pk=None):
        """Place an order (move from draft to pending)."""
        order = self.get_object()
        order.place_order()
        serializer = OrderSerializer(order)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        """Mark order as delivered."""
        order = self.get_object()
        order.mark_delivered()
        serializer = OrderSerializer(order)
        return Response(serializer.data)


# API Endpoints for Larder Microservice Integration


class ProductMasterViewSet(viewsets.ModelViewSet):
    """
    API endpoints for ProductMaster (OFF products).
    Used by larder microservice to get and create product nutrition data.
    
    GET: List, search, filter products (read-only)
    POST: Create product from OFF data (from larder microservice)
    """
    queryset = ProductMaster.objects.all()
    serializer_class = ProductMasterSerializer
    permission_classes = [AllowAny]
    filter_backends = [SearchFilter]
    search_fields = ['name', 'brand', 'barcode']
    
    def perform_create(self, serializer):
        """Validate barcode is unique before saving."""
        barcode = self.request.data.get('barcode')
        if ProductMaster.objects.filter(barcode=barcode).exists():
            return Response(
                {'error': 'Product with this barcode already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def by_barcode(self, request):
        """Get product by barcode."""
        barcode = request.query_params.get('barcode')
        if not barcode:
            return Response({'error': 'barcode parameter required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = ProductMaster.objects.get(barcode=barcode)
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        except ProductMaster.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)


class GroceryStoreViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for querying GroceryStore.
    Used by larder microservice for store/location data.
    """
    queryset = GroceryStore.objects.all()
    serializer_class = GroceryStoreSerializer
    permission_classes = [AllowAny]


class TokenVerifyView(APIView):
    """
    Verify JWT token and return user information.
    Used by larder microservice for SSO token validation.
    
    Endpoint: GET /api/auth/verify/
    Header: Authorization: Bearer <jwt_token>
    
    Returns: {id, email, first_name, last_name}
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
        })
