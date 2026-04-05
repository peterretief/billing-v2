from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from google import genai
from firecrawl import FirecrawlApp
import json
from decimal import Decimal
from django.utils import timezone

from .models import (
    MarketPrice, Ingredient, Recipe, RecipeComponent, Menu,
    MealPlan, MealPlanDay, ShoppingList,
    LarderItem, build_larder_prompt,
    PriceSource,
    UserPreference, generate_meal_plan, generate_shopping_list,
)
from .forms import (
    LarderConsumeForm, LarderItemForm, MealPlanGenerateForm,
    PriceSourceForm, SwapMealForm, UserPreferenceForm,
)
from inventory.models import InventoryItem, StockTransaction

@login_required
def stock_purchased_ingredients(request):
    """
    Action: Records shopping list items into physical inventory.
    """
    if request.method == 'POST':
        # Expects a list of ingredient_id and qty
        ingredient_ids = request.POST.getlist('ingredient_ids')
        qtys = request.POST.getlist('qtys')
        
        success_count = 0
        for ing_id, qty in zip(ingredient_ids, qtys):
            ingredient = get_object_or_404(Ingredient, id=ing_id, user=request.user)
            if ingredient.inventory_item:
                # Add to inventory
                qty_decimal = Decimal(qty)
                item = ingredient.inventory_item
                item.current_stock += qty_decimal
                item.save()
                
                # Create audit trail
                StockTransaction.objects.create(
                    user=request.user,
                    inventory_item=item,
                    transaction_type='IN',
                    quantity=qty_decimal,
                    notes=f"Purchased for recipes via Shopping List"
                )
                success_count += 1
        
        messages.success(request, f"Successfully stocked {success_count} items into your inventory!")
        return redirect('inventory:item_list')
    
    return redirect('recipes:shopping_list')

@login_required
def shopping_list(request):
    headcount = int(request.GET.get('headcount', 10))
    summary = {}
    recipes = Recipe.objects.filter(user=request.user)
    
    for recipe in recipes:
        factor = Decimal(str(headcount / recipe.servings_yield))
        for comp in recipe.components.all():
            name = comp.ingredient.name
            qty = comp.quantity_used * factor
            cost = comp.component_cost * factor
            
            if name not in summary:
                summary[name] = {
                    'qty': 0, 
                    'cost': 0, 
                    'unit': comp.ingredient.unit, 
                    'ingredient_id': comp.ingredient.id,
                    'is_linked': comp.ingredient.inventory_item is not None
                }
            summary[name]['qty'] += qty
            summary[name]['cost'] += cost

    return render(request, 'recipes/shopping_list.html', {
        'summary': summary, 
        'headcount': headcount
    })

# ... (Previous views: import_from_text, scrape_recipe, recipe_dashboard, market_explorer, etc. kept below)

@login_required
def import_from_text(request):
    """
    Parses a plain text list of ingredients into the system using robust AI extraction.
    """
    if request.method == 'POST':
        text = request.POST.get('text')
        if not text:
            messages.error(request, "Please provide some text to parse.")
            return redirect('recipes:recipe_dashboard')

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        try:
            prompt = (
                "Extract this recipe text into a structured JSON object. "
                "Return exactly one JSON object with: "
                "- name: string title "
                "- servings: integer "
                "- instructions: string method "
                "- ingredients: list of objects with {'name': string, 'qty': float, 'unit': string} "
                f"\n\nTEXT TO PARSE:\n{text}"
            )
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt, 
                config={'response_mime_type': 'application/json'}
            )
            
            data = json.loads(response.text.strip())
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            
            if not isinstance(data, dict):
                raise ValueError("Invalid AI response format.")

            recipe = Recipe.objects.create(
                user=request.user, 
                name=data.get('name') or 'Imported Recipe', 
                instructions=data.get('instructions') or '',
                servings_yield=data.get('servings') or 1
            )

            # Robust ingredient processing
            ingredients_list = data.get('ingredients', [])
            if not isinstance(ingredients_list, list):
                ingredients_list = []

            for ing_data in ingredients_list:
                if isinstance(ing_data, str):
                    name, qty, unit = ing_data.title(), 1.0, 'unit'
                else:
                    name = str(ing_data.get('name', 'Unknown')).title()
                    qty = float(ing_data.get('qty') or 1.0)
                    unit = str(ing_data.get('unit') or 'unit')

                ing, _ = Ingredient.objects.get_or_create(
                    user=request.user, 
                    name=name, 
                    defaults={'unit': unit, 'purchase_quantity': 1.0}
                )
                RecipeComponent.objects.create(
                    user=request.user, 
                    recipe=recipe, 
                    ingredient=ing, 
                    quantity_used=qty
                )
            
            messages.success(request, f"Imported '{recipe.name}' with {len(ingredients_list)} ingredients.")
            return redirect('recipes:recipe_detail', pk=recipe.pk)
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")
            return redirect('recipes:recipe_dashboard')
    return render(request, 'recipes/import_text_form.html')

@login_required
def scrape_recipe(request):
    """
    Magic Import via URL with robust fault tolerance.
    """
    if request.method == 'POST':
        url = request.POST.get('url')
        if not url: return redirect('recipes:recipe_list')
        
        firecrawl = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        try:
            scrape_result = firecrawl.scrape(url=url, formats=['markdown'])
            markdown_content = scrape_result.get('markdown', '') if isinstance(scrape_result, dict) else scrape_result.markdown
            
            prompt = (
                "Extract this recipe into a structured JSON object. "
                "Return exactly one JSON object with: "
                "- name: string title "
                "- servings: integer "
                "- instructions: string method "
                "- ingredients: list of objects with {'name': string, 'qty': float, 'unit': string} "
                f"\n\nDATA:\n{markdown_content}"
            )
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt, 
                config={'response_mime_type': 'application/json'}
            )
            
            data = json.loads(response.text.strip())
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            recipe = Recipe.objects.create(
                user=request.user, 
                name=data.get('name') or 'Imported Recipe', 
                instructions=data.get('instructions') or '', 
                servings_yield=data.get('servings') or 1
            )

            ingredients_list = data.get('ingredients', [])
            if not isinstance(ingredients_list, list):
                ingredients_list = []

            for ing_data in ingredients_list:
                if isinstance(ing_data, str):
                    name, qty, unit = ing_data.title(), 1.0, 'unit'
                else:
                    name = str(ing_data.get('name', 'Unknown')).title()
                    qty = float(ing_data.get('qty') or 1.0)
                    unit = str(ing_data.get('unit') or 'unit')

                ingredient, _ = Ingredient.objects.get_or_create(
                    user=request.user, name=name, defaults={'unit': unit, 'purchase_quantity': 1.0}
                )
                RecipeComponent.objects.create(
                    user=request.user, recipe=recipe, ingredient=ingredient, quantity_used=qty
                )
            
            messages.success(request, f"Imported '{recipe.name}' from web.")
            return redirect('recipes:recipe_detail', pk=recipe.pk)
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")
            return redirect('recipes:recipe_list')
    return render(request, 'recipes/scrape_recipe_form.html')

@login_required
def recipe_dashboard(request):
    recipes = Recipe.objects.filter(user=request.user)
    ingredients = Ingredient.objects.filter(user=request.user)
    total_recipes = recipes.count()
    linked_ingredients = ingredients.filter(market_ref__isnull=False).count()
    unlinked_ingredients = ingredients.filter(market_ref__isnull=True).count()
    expensive_recipes = sorted(recipes, key=lambda r: r.total_cost, reverse=True)[:5]

    larder_items = list(LarderItem.objects.filter(user=request.user))
    urgent_larder_count = sum(1 for i in larder_items if i.urgency in ("expired", "critical"))
    larder_total = len(larder_items)

    latest_plan = MealPlan.objects.filter(user=request.user).order_by('-start_date').first()

    return render(request, 'recipes/dashboard.html', {
        'total_recipes': total_recipes,
        'linked_ingredients': linked_ingredients,
        'unlinked_ingredients': unlinked_ingredients,
        'market_items_count': MarketPrice.objects.count(),
        'expensive_recipes': expensive_recipes,
        'urgent_larder_count': urgent_larder_count,
        'larder_total': larder_total,
        'latest_plan': latest_plan,
    })

@login_required
def market_explorer(request):
    query = request.GET.get('q', '')
    market_items = MarketPrice.objects.filter(commodity__icontains=query) if query else MarketPrice.objects.all().order_by('commodity')
    return render(request, 'recipes/market_explorer.html', {'items': market_items, 'query': query})

@login_required
def link_ingredient_to_market(request, ingredient_id):
    ingredient = get_object_or_404(Ingredient, id=ingredient_id, user=request.user)
    if request.method == 'POST':
        market_item = get_object_or_404(MarketPrice, id=request.POST.get('market_id'))
        ingredient.market_ref = market_item
        ingredient.purchase_value = market_item.total_price
        ingredient.save()
        return redirect('recipes:recipe_dashboard')
    query = request.GET.get('q', '')
    items = MarketPrice.objects.filter(commodity__icontains=query) if query else MarketPrice.objects.all()[:100]
    return render(request, 'recipes/link_to_market.html', {'ingredient': ingredient, 'items': items, 'query': query})

@login_required
def recipe_list(request):
    return render(request, 'recipes/recipe_list.html', {'recipes': Recipe.objects.filter(user=request.user)})

@login_required
def recipe_detail(request, pk):
    return render(request, 'recipes/recipe_detail.html', {'recipe': get_object_or_404(Recipe, pk=pk, user=request.user)})

@login_required
def recipe_create(request):
    messages.info(request, "Use 'Scrape' or 'Import' for now!")
    return redirect('recipes:recipe_list')

@login_required
def recipe_update(request, pk):
    messages.info(request, "Development in progress.")
    return redirect('recipes:recipe_list')


# ---------------------------------------------------------------------------
# Dietary Preferences
# ---------------------------------------------------------------------------

@login_required
def preferences(request):
    """View and edit the user's dietary preferences."""
    pref = UserPreference.for_user(request.user)
    if request.method == 'POST':
        form = UserPreferenceForm(request.POST, instance=pref, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences saved.")
            return redirect('recipes:preferences')
    else:
        form = UserPreferenceForm(instance=pref, user=request.user)
    return render(request, 'recipes/preferences.html', {'form': form, 'pref': pref})


# ---------------------------------------------------------------------------
# Meal Plan
# ---------------------------------------------------------------------------

@login_required
def meal_plan_generate(request):
    """Generate a new meal plan for a date range."""
    if request.method == 'POST':
        form = MealPlanGenerateForm(request.POST)
        if form.is_valid():
            meal_plan = generate_meal_plan(
                user=request.user,
                title=form.get_title(),
                start_date=form.cleaned_data['start_date'],
                end_date=form.cleaned_data['end_date'],
            )
            messages.success(request, f"Meal plan '{meal_plan.title}' created for {meal_plan.total_days} day(s).")
            return redirect('recipes:meal_plan_detail', pk=meal_plan.pk)
    else:
        form = MealPlanGenerateForm()
    return render(request, 'recipes/meal_plan_generate.html', {'form': form})


@login_required
def meal_plan_list(request):
    """List all meal plans for the current user."""
    plans = MealPlan.objects.filter(user=request.user)
    return render(request, 'recipes/meal_plan_list.html', {'plans': plans})


@login_required
def meal_plan_delete(request, pk):
    """Delete a meal plan (POST only)."""
    meal_plan = get_object_or_404(MealPlan, pk=pk, user=request.user)
    if request.method == 'POST':
        title = meal_plan.title
        meal_plan.delete()
        messages.success(request, f"Meal plan '{title}' removed.")
    return redirect('recipes:meal_plan_list')


@login_required
def meal_plan_detail(request, pk):
    """View a meal plan with all days and meals."""
    meal_plan = get_object_or_404(MealPlan, pk=pk, user=request.user)
    days = meal_plan.days.select_related('breakfast', 'lunch', 'dinner').order_by('date')
    has_shopping_list = ShoppingList.objects.filter(meal_plan=meal_plan).exists()
    return render(request, 'recipes/meal_plan_detail.html', {
        'meal_plan': meal_plan,
        'days': days,
        'has_shopping_list': has_shopping_list,
    })


@login_required
def meal_plan_swap(request, plan_id, day_id):
    """Swap a recipe on a specific day/meal slot."""
    meal_plan = get_object_or_404(MealPlan, pk=plan_id, user=request.user)
    day = get_object_or_404(MealPlanDay, pk=day_id, meal_plan=meal_plan)

    if request.method == 'POST':
        form = SwapMealForm(request.POST)
        if form.is_valid():
            try:
                recipe = form.get_recipe(request.user)
                day.set_meal(form.cleaned_data['slot'], recipe)
                # Invalidate shopping list so it gets regenerated
                ShoppingList.objects.filter(meal_plan=meal_plan).delete()
                messages.success(request, f"Swapped {form.cleaned_data['slot']} on {day.date}.")
            except Recipe.DoesNotExist:
                messages.error(request, "Recipe not found.")
        else:
            messages.error(request, "Invalid swap request.")
        return redirect('recipes:meal_plan_detail', pk=plan_id)

    # GET: show a recipe picker for the given slot
    slot = request.GET.get('slot', 'dinner')
    available_recipes = Recipe.objects.filter(user=request.user).order_by('name')
    current_recipe = getattr(day, slot, None)
    return render(request, 'recipes/meal_plan_swap.html', {
        'meal_plan': meal_plan,
        'day': day,
        'slot': slot,
        'current_recipe': current_recipe,
        'available_recipes': available_recipes,
    })


# ---------------------------------------------------------------------------
# Shopping List (from Meal Plan)
# ---------------------------------------------------------------------------

@login_required
def meal_plan_shopping_list(request, plan_id):
    """Get or generate the shopping list for a meal plan, grouped by store."""
    meal_plan = get_object_or_404(MealPlan, pk=plan_id, user=request.user)

    if request.method == 'POST' and request.POST.get('action') == 'regenerate':
        sl = generate_shopping_list(meal_plan)
        messages.success(request, "Shopping list regenerated.")
        return redirect('recipes:meal_plan_shopping_list', plan_id=plan_id)

    try:
        sl = meal_plan.shopping_list
    except ShoppingList.DoesNotExist:
        sl = generate_shopping_list(meal_plan)
        messages.info(request, "Shopping list generated.")

    return render(request, 'recipes/meal_plan_shopping_list.html', {
        'meal_plan': meal_plan,
        'shopping_list': sl,
        'items_by_store': sl.items_by_store,
        'cost_by_store': sl.cost_by_store,
    })


@login_required
def shopping_list_item_purchased(request, plan_id, item_id):
    """
    Mark a shopping list item as purchased and add the bought quantity to the larder.

    This closes the loop:
        Shopping list says "buy 995 g stock powder"
        → User buys it
        → Clicks this button
        → 995 g stock powder appears in the larder
        → Next meal plan generation deducts it from the shopping cost
    """
    meal_plan = get_object_or_404(MealPlan, pk=plan_id, user=request.user)
    item = get_object_or_404(ShoppingList.objects.get(meal_plan=meal_plan).items, pk=item_id)

    if request.method == 'POST' and item.quantity_to_buy > 0:
        ing = item.ingredient
        LarderItem.objects.create(
            user=request.user,
            ingredient=ing,
            name=ing.name,
            quantity=item.quantity_to_buy,
            unit=item.unit,
            cost_per_unit=ing.price_per_unit,
        )
        messages.success(
            request,
            f"Added {item.quantity_to_buy} {item.unit} of {ing.name} to your larder."
        )

    return redirect('recipes:meal_plan_shopping_list', plan_id=plan_id)


# ---------------------------------------------------------------------------
# Larder (Pantry)
# ---------------------------------------------------------------------------

@login_required
def larder_dashboard(request):
    """Overview of the larder, grouped by urgency."""
    all_items = list(LarderItem.objects.filter(user=request.user))
    critical = [i for i in all_items if i.urgency in ("expired", "critical")]
    warning  = [i for i in all_items if i.urgency == "warning"]
    ok       = [i for i in all_items if i.urgency == "ok"]
    staples  = [i for i in all_items if i.urgency == "staple"]
    return render(request, 'recipes/larder_dashboard.html', {
        'critical': critical,
        'warning': warning,
        'ok': ok,
        'staples': staples,
        'total_value': sum(i.total_value for i in all_items),
        'has_urgent': bool(critical),
    })


@login_required
def larder_add(request):
    """Add a new item to the larder."""
    if request.method == 'POST':
        form = LarderItemForm(request.POST, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            messages.success(request, f"'{item.name}' added to your larder.")
            return redirect('recipes:larder_dashboard')
    else:
        # Pre-populate from inventory if ?from_inventory=<id>
        initial = {}
        inv_id = request.GET.get('from_inventory')
        if inv_id:
            try:
                inv = InventoryItem.objects.get(pk=inv_id, user=request.user)
                initial = {
                    'name': inv.name,
                    'quantity': inv.current_stock,
                    'unit': inv.unit_of_measure,
                    'cost_per_unit': inv.buy_price or Decimal('0'),
                }
            except InventoryItem.DoesNotExist:
                pass
        form = LarderItemForm(initial=initial, user=request.user)
    return render(request, 'recipes/larder_form.html', {'form': form, 'action': 'Add'})


@login_required
def larder_edit(request, pk):
    """Edit an existing larder item."""
    item = get_object_or_404(LarderItem, pk=pk, user=request.user)
    if request.method == 'POST':
        form = LarderItemForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{item.name}' updated.")
            return redirect('recipes:larder_dashboard')
    else:
        form = LarderItemForm(instance=item, user=request.user)
    return render(request, 'recipes/larder_form.html', {'form': form, 'item': item, 'action': 'Edit'})


@login_required
def larder_delete(request, pk):
    """Remove an item from the larder (POST only)."""
    item = get_object_or_404(LarderItem, pk=pk, user=request.user)
    if request.method == 'POST':
        name = item.name
        item.delete()
        messages.success(request, f"'{name}' removed from larder.")
    return redirect('recipes:larder_dashboard')


@login_required
def larder_consume(request, pk):
    """Reduce a larder item's quantity after cooking."""
    item = get_object_or_404(LarderItem, pk=pk, user=request.user)
    if request.method == 'POST':
        form = LarderConsumeForm(request.POST)
        if form.is_valid():
            qty = form.cleaned_data['qty_used']
            name = item.name
            deleted = item.consume(qty)
            if deleted:
                messages.success(request, f"'{name}' fully used and removed.")
            else:
                messages.success(request, f"Updated: {item.quantity} {item.unit} of '{item.name}' remaining.")
    return redirect('recipes:larder_dashboard')


@login_required
def larder_cook(request):
    """
    AI-powered 'Cook from Larder' view.
    GET  — shows the current larder state and the AI prompt that will be sent.
    POST — calls Gemini, saves the generated recipe, redirects to its detail page.
    """
    system_prompt, user_prompt, has_must_use = build_larder_prompt(request.user)

    if not user_prompt.strip():
        messages.warning(request, "Your larder is empty. Add some items first.")
        return redirect('recipes:larder_add')

    if request.method == 'POST':
        full_prompt = f"System: {system_prompt}\n\nUser:\n{user_prompt}"
        try:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt,
                config={'response_mime_type': 'application/json'},
            )
            data = json.loads(response.text.strip())
            if isinstance(data, list):
                data = data[0]

            recipe = Recipe.objects.create(
                user=request.user,
                name=data.get('name', 'Larder Recipe'),
                instructions=data.get('instructions', ''),
                servings_yield=int(data.get('servings') or 1),
            )
            for ing_data in data.get('ingredients', []):
                if isinstance(ing_data, str):
                    name, qty, unit = ing_data.title(), 1.0, 'unit'
                else:
                    name = str(ing_data.get('name', 'Unknown')).title()
                    qty = float(ing_data.get('qty') or 1.0)
                    unit = str(ing_data.get('unit') or 'unit')
                ing, _ = Ingredient.objects.get_or_create(
                    user=request.user, name=name,
                    defaults={'unit': unit, 'purchase_quantity': Decimal('1.0')},
                )
                RecipeComponent.objects.create(
                    user=request.user, recipe=recipe, ingredient=ing, quantity_used=qty,
                )

            messages.success(request, f"Recipe '{recipe.name}' generated and saved to your recipe book!")
            return redirect('recipes:recipe_detail', pk=recipe.pk)

        except Exception as e:
            messages.error(request, f"AI generation failed: {e}")

    all_items = list(LarderItem.objects.filter(user=request.user))
    return render(request, 'recipes/larder_cook.html', {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
        'has_must_use': has_must_use,
        'critical': [i for i in all_items if i.urgency in ("expired", "critical")],
        'warning': [i for i in all_items if i.urgency == "warning"],
    })


# ---------------------------------------------------------------------------
# Market Price Sources (scraper management)
# ---------------------------------------------------------------------------

def _run_scrape(source):
    """
    Scrape a PriceSource URL with Firecrawl, parse with Gemini, and sync
    results into MarketPrice. Returns the number of items updated.
    Raises on unrecoverable errors; stores soft errors on the source record.
    """
    firecrawl = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    scrape_result = firecrawl.scrape(url=source.url, formats=['markdown'])
    markdown = (
        scrape_result.markdown
        if hasattr(scrape_result, 'markdown')
        else scrape_result.get('markdown', '')
    )

    if not markdown or len(markdown.strip()) < 50:
        raise ValueError("Scraped page returned no usable content.")

    extra_hint = f"\nContext for this source: {source.notes}" if source.notes else ""
    lines = markdown.split('\n')
    batch_size = 80
    all_items = []

    for i in range(0, len(lines), batch_size):
        batch = '\n'.join(lines[i:i + batch_size])
        if len(batch.strip()) < 50:
            continue
        prompt = (
            "Extract grocery/produce price items from this data chunk into a JSON array. "
            "Each object must have: sku_key (short unique code), commodity (full name), "
            "variety (variety or type), weight (numeric kg), class_size (grade/size), "
            f"total_price (average price as decimal).{extra_hint}"
            "\nReturn ONLY a JSON array — no explanation."
            f"\n\nDATA:\n{batch}"
        )
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config={'response_mime_type': 'application/json'},
            )
            batch_items = json.loads(response.text.strip())
            if isinstance(batch_items, list):
                all_items.extend(batch_items)
        except Exception:
            continue  # Skip bad batches, keep going

    updated = 0
    for item in all_items:
        raw_sku = str(item.get('sku_key', '')).strip()
        if not raw_sku:
            continue
        # Namespace sku_key per source so different suppliers don't collide
        sku_key = f"{source.slug}__{raw_sku}"[:100]
        try:
            MarketPrice.objects.update_or_create(
                sku_key=sku_key,
                defaults={
                    'commodity': str(item.get('commodity', '')).strip()[:100],
                    'variety': str(item.get('variety', '')).strip()[:100],
                    'weight': Decimal(str(item.get('weight') or '0')),
                    'class_size': str(item.get('class_size', 'N/A'))[:20],
                    'total_price': Decimal(str(item.get('total_price') or '0')),
                    'source': source,
                },
            )
            updated += 1
        except Exception:
            continue

    source.last_scraped = timezone.now()
    source.last_item_count = updated
    source.last_error = ''
    source.save(update_fields=['last_scraped', 'last_item_count', 'last_error'])
    return updated


@login_required
def market_sources(request):
    """List all configured price sources with stats, and browse recent prices."""
    sources = PriceSource.objects.all()
    total_prices = MarketPrice.objects.count()
    recent_prices = MarketPrice.objects.select_related('source').order_by('-last_updated')[:20]
    return render(request, 'recipes/market_sources.html', {
        'sources': sources,
        'total_prices': total_prices,
        'recent_prices': recent_prices,
    })


@login_required
def market_source_add(request):
    """Add a new price source."""
    if request.method == 'POST':
        form = PriceSourceForm(request.POST)
        if form.is_valid():
            source = form.save()
            messages.success(request, f"'{source.name}' added. Run a scrape to populate prices.")
            return redirect('recipes:market_sources')
    else:
        form = PriceSourceForm()
    return render(request, 'recipes/market_source_form.html', {'form': form, 'action': 'Add'})


@login_required
def market_source_edit(request, pk):
    """Edit a price source."""
    source = get_object_or_404(PriceSource, pk=pk)
    if request.method == 'POST':
        form = PriceSourceForm(request.POST, instance=source)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{source.name}' updated.")
            return redirect('recipes:market_sources')
    else:
        form = PriceSourceForm(instance=source)
    return render(request, 'recipes/market_source_form.html', {'form': form, 'source': source, 'action': 'Edit'})


@login_required
def market_source_delete(request, pk):
    """Delete a price source (POST only)."""
    source = get_object_or_404(PriceSource, pk=pk)
    if request.method == 'POST':
        name = source.name
        source.delete()
        messages.success(request, f"'{name}' removed.")
    return redirect('recipes:market_sources')


@login_required
def market_source_scrape(request, pk):
    """
    Trigger a live scrape for a price source.
    Runs synchronously — redirects back with a success/error message.
    """
    source = get_object_or_404(PriceSource, pk=pk)
    if request.method == 'POST':
        try:
            count = _run_scrape(source)
            messages.success(request, f"Scrape complete: {count} price{'s' if count != 1 else ''} updated from {source.name}.")
        except Exception as e:
            source.last_error = str(e)
            source.save(update_fields=['last_error'])
            messages.error(request, f"Scrape failed for {source.name}: {e}")
    return redirect('recipes:market_sources')
