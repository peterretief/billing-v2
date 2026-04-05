# Meal Planning System - Complete Guide

## Overview

The Larder meal planning system provides intelligent, automated meal planning with recipe management, dietary preference support, and shopping list generation. It's designed for flexible meal planning with multi-user support.

## Architecture

### Core Models

```
Criteria
  ├─ Defines dietary preferences (vegetarian, vegan, allergen exclusions)
  └─ Links to recipes matching the criteria

Recipe
  ├─ Contains nutritional data (calories, protein, carbs, fat)
  ├─ Tracks allergens and dietary flags
  ├─ Many-to-many with Ingredient (through product catalog)
  └─ Supports prep/cook time tracking

Menu (Breakfast, Lunch, Dinner)
  ├─ Groups recipes by meal period
  ├─ Optional dietary criteria
  └─ Many-to-many with recipes through MenuRecipe (ordered)

MealPlan (Weekly, Daily, Custom)
  ├─ Defined by date range
  ├─ Auto-populates MealPlanDay records on creation
  └─ Links to shopping lists

MealPlanDay
  ├─ One per day in meal plan
  ├─ Many-to-many with Menus
  └─ Aggregates ingredients for that day

ShoppingList
  ├─ Generated from MealPlan
  ├─ Aggregates all ingredients needed
  ├─ Tracks purchase status
  └─ Linked to One or more Orders

ShoppingListItem
  ├─ Individual item in shopping list
  ├─ Tracks quantity, unit, estimated cost
  ├─ Mark as purchased
  └─ Supports bulk purchase status updates

Order
  ├─ Created from ShoppingList
  ├─ Links to GroceryStore
  ├─ Tracks status (draft → pending → delivered)
  └─ Records total amount and delivery dates
```

## API Endpoints

### Meal Plan Generation

#### Quick Generate
```bash
POST /api/meal-plans/generate_quick/
Content-Type: application/json

{
  "name": "Weekly Plan",
  "days": 7,
  "criteria_id": 2  # Optional: dietary criteria to apply
}

Response:
{
  "id": 1,
  "name": "Weekly Plan",
  "start_date": "2026-04-05",
  "end_date": "2026-04-11",
  "time_period": "weekly",
  "meal_plan_days": [...]
}
```

#### Generate Shopping List
```bash
POST /api/meal-plans/{id}/generate_shopping_list/

Response:
{
  "id": 5,
  "name": "Shopping List - Weekly Plan",
  "meal_plan": 1,
  "total_cost": 250.50,
  "is_purchased": false,
  "items": [
    {
      "id": 1,
      "product": "Chicken Breast",
      "quantity": 2,
      "unit": "kg",
      "estimated_cost": 150.00,
      "purchased": false
    },
    ...
  ]
}
```

### Meal Plan Optimization

#### Check Nutrition Balance
```bash
POST /api/meal-plans/{id}/suggest_balance/
Content-Type: application/json

{
  "target_calories": 2000
}

Response:
{
  "recommendations": [
    {
      "date": "2026-04-05",
      "issue": "Calories: 1850 (target: 2000)",
      "severity": "medium"
    }
  ]
}
```

#### Check Recipe Variety
```bash
POST /api/meal-plans/{id}/check_variety/

Response:
{
  "recommendations": [
    {
      "recipe": "Grilled Chicken",
      "frequency": 4,
      "suggestion": "Consider alternative for Grilled Chicken"
    }
  ]
}
```

#### Bulk Assign Menus
```bash
POST /api/meal-plans/{id}/bulk_assign_menus/
Content-Type: application/json

{
  "menu_ids": [1, 2, 3],
  "day_type": "weekdays"  # 'all', 'weekdays', 'weekends'
}

Response:
{
  "status": "success",
  "message": "Assigned 3 menus"
}
```

### Shopping List Management

#### Mark All Items Purchased
```bash
POST /api/shopping-lists/{id}/mark_purchased/

Response:
{
  "id": 5,
  "is_purchased": true,
  "purchased_at": "2026-04-05T14:30:00Z"
}
```

#### Mark Individual Item Purchased
```bash
POST /api/shopping-lists/{id}/mark_item_purchased/
Content-Type: application/json

{
  "item_id": 15
}

Response:
{
  "status": "success",
  "item_id": 15
}
```

### Menu Suggestions

#### Suggest Recipes for Menu
```bash
GET /api/menus/{id}/suggest_recipes/?exclude=1,2,3

Response:
[
  {
    "id": 5,
    "name": "Vegetable Stir Fry",
    "calories": 450,
    "is_vegetarian": true,
    "ingredients": [...]
  },
  ...
]
```

## Usage Workflows

### Workflow 1: Quick Weekly Meal Plan

1. Create dietary criteria (optional)
   ```python
   criteria = Criteria.objects.create(
       user=request.user,
       name="Keto",
       vegetarian=False,
       vegan=False,
       max_calories=2000
   )
   ```

2. Generate meal plan
   ```python
   POST /api/meal-plans/generate_quick/
   {
     "name": "Week of April 5",
     "days": 7,
     "criteria_id": 1
   }
   ```

3. View suggested menus for each day
   - Accessed via `/api/meal-plans/{id}/`
   - Shows all MealPlanDay records with assigned menus

4. Generate shopping list
   ```python
   POST /api/meal-plans/{id}/generate_shopping_list/
   ```

5. Place order
   ```python
   POST /api/shopping-lists/{id}/place_order/
   {
     "store_id": 1
   }
   ```

6. Track purchase
   ```python
   POST /api/shopping-lists/{id}/mark_purchased/
   ```

### Workflow 2: Custom Meal Plan

1. Create menus for each meal period
   ```python
   POST /api/menus/
   {
     "name": "Breakfast - Eggs",
     "meal_period": "breakfast",
     "recipes": [1, 2, 3]
   }
   ```

2. Create meal plan
   ```python
   POST /api/meal-plans/
   {
     "name": "Custom Plan",
     "start_date": "2026-04-05",
     "end_date": "2026-04-11",
     "time_period": "custom"
   }
   ```

3. Assign menus manually
   ```python
   PUT /api/meal-plan-days/{id}/
   {
     "menus": [1, 2, 3]
   }
   ```
   Or use bulk assignment:
   ```python
   POST /api/meal-plans/{id}/bulk_assign_menus/
   {
     "menu_ids": [1, 2, 3],
     "day_type": "weekdays"
   }
   ```

4. Generate shopping list and complete purchase


### Workflow 3: Optimize Existing Plan

1. Check nutrition balance
   ```python
   POST /api/meal-plans/{id}/suggest_balance/
   {
     "target_calories": 2000
   }
   ```

2. Review recommendations
   - Identify days with calorie mismatches
   - Understand protein/carb ratios

3. Check recipe variety
   ```python
   POST /api/meal-plans/{id}/check_variety/
   ```

4. Make adjustments
   - Swap recipes on specific days
   - Use suggest_recipes to find alternatives
   - Re-generate shopping list

## Service Layer

### MealPlanGenerator

Handles intelligent meal plan creation and shopping list generation.

```python
from larder.meal_planning_service import MealPlanGenerator

generator = MealPlanGenerator(user, criteria)
meal_plan = generator.generate_meal_plan(
    name="Weekly Plan",
    start_date=date(2026, 4, 5),
    end_date=date(2026, 4, 11),
    criteria=criteria  # Optional
)

shopping_list = generator.generate_shopping_list(meal_plan)
```

#### Features

- **Dietary Respect**: Filters recipes by criteria (vegetarian, vegan, allergens)
- **Variety Tracking**: Avoids repeating recipes within a time period
- **Smart Selection**: Scores menus by recipe variety
- **Ingredient Aggregation**: Combines quantities intelligently
- **Cost Estimation**: Pulls from ProductPrice if available

### MealPlanOptimizer

Provides recommendations for meal plan improvements.

```python
from larder.meal_planning_service import MealPlanOptimizer

# Check nutrition
recommendations = MealPlanOptimizer.balance_nutrition(
    meal_plan,
    target_calories=2000,
    target_protein_percent=30
)

# Check variety
recommendations = MealPlanOptimizer.maximize_variety(meal_plan)
```

#### Recommendations

- **Nutrition**: Flags days outside ±10% of targets
- **Variety**: Suggests alternatives for recipes appearing 2+ times per week
- **Cost**: Framework for ingredient cost optimization

### Helper Functions

```python
from larder.meal_planning_service import (
    quick_generate_meal_plan,      # 7-line convenience wrapper
    auto_create_shopping_list,     # Generate from meal plan
    bulk_assign_menus_to_days,     # Assign to weekdays/weekends
    suggest_recipes_for_menu       # Filter by criteria & meal period
)

# Quick generation
meal_plan = quick_generate_meal_plan(
    user=request.user,
    name="Weekly",
    days=7,
    criteria=criteria
)

# Bulk assign same menus
menus = Menu.objects.filter(meal_period='breakfast')
bulk_assign_menus_to_days(meal_plan, menus, day_type='weekdays')

# Suggest recipes
recipes = suggest_recipes_for_menu(
    user=request.user,
    meal_period='dinner',
    criteria=criteria,
    exclude_recipes=[1, 2, 3]
)
```

## Template Views

### Web UI Endpoints

| Path | Purpose |
|------|---------|
| `/larder/recipes/` | Browse all recipes |
| `/larder/recipes/create/` | Create new recipe |
| `/larder/recipes/<id>/` | Recipe detail with ingredients |
| `/larder/menus/` | Browse menus grouped by period |
| `/larder/menus/create/` | Create menu with recipe selection |
| `/larder/meal-plans/` | View all meal plans |
| `/larder/meal-plans/create/` | Create meal plan with date range |
| `/larder/meal-plans/<id>/` | **Calendar view** with daily menus |
| `/larder/meal-plan-days/<id>/edit/` | Assign menus to specific day |
| `/larder/shopping-lists/` | Browse shopping lists |
| `/larder/shopping-lists/<id>/` | List items with checkboxes |
| `/larder/orders/` | Manage orders by status |
| `/larder/orders/<id>/` | Order detail with tracking |

### Calendar Features

The mealplan_detail.html template provides:
- Date column with weekday
- Assigned menus for each day
- Recipe preview
- Quick edit links to adjust
- Ingredient summary panel
- Shopping list status

## Database Schema

### Key Relationships

```sql
-- Shopping list with items
shopping_list (1) --- (*) shopping_list_item
shopping_list (1) --- (*) order

-- Meal plan with daily assignments
meal_plan (1) --- (*) meal_plan_day (date)
meal_plan_day (*) --- (*) menu (through M2M)

-- Menu with recipes
menu (*) --- (*) recipe (through menu_recipe with order field)
recipe (*) --- (*) ingredient (through product FK)

-- Criteria for filtering
criteria (*) --- (*) recipe (through get_matching_recipes method)
```

### Indexes

```sql
-- For fast user-scoped queries
CREATE INDEX ON meal_plan(user_id);
CREATE INDEX ON shopping_list(user_id);
CREATE INDEX ON order(user_id, status);

-- For item lookups
CREATE INDEX ON shopping_list_item(shopping_list_id);
CREATE UNIQUE INDEX ON shopping_list_item(shopping_list_id, product_id);
```

## Performance Considerations

### Query Optimization

1. **Prefetch Related**: Use `prefetch_related` for M2M relationships
   ```python
   MealPlan.objects.filter(user=user).prefetch_related(
       'meal_plan_days__menus__recipes__ingredients'
   )
   ```

2. **Aggregation**: Use `aggregate()` for counts and summaries
   ```python
   ShoppingListItem.objects.filter(shopping_list=sl).aggregate(
       total_cost=Sum('estimated_cost'),
       item_count=Count('id')
   )
   ```

3. **Select For Update**: Lock shopping list during purchase marking
   ```python
   sl = ShoppingList.objects.select_for_update().get(pk=id)
   ```

### Caching Opportunities

- Recipe suggestions (stable per user/criteria)
- Criteria definitions (rarely change)
- Menu periods (static choices)

## Limitations & Future Work

### Current Limitations

1. **Meal period assignment**: Currently simple (breakfast/lunch/dinner)
   - Could add snacks, drinks, etc.

2. **Ingredient quantities**: Simplified unit system (g, kg, ml, l, unit)
   - Could expand to tbsp, tsp, cups, etc.

3. **Cost estimation**: Requires ProductPrice records
   - Falls back to None if not available

4. **Scheduling**: Daily assignments only
   - Could support recurring assignments (e.g., Eggs every Monday)

### Future Enhancements

1. **Meal Generation Algorithm**
   - Machine learning to optimize based on past choices
   - Seasonal ingredient preference

2. **Restaurant Integration**
   - Look up recipes from restaurant menus
   - Calculate costs in real-time

3. **Nutritionist Collaboration**
   - Share meal plans with nutritionists
   - Get professional feedback

4. **Inventory Sync**
   - Track items used from larder inventory
   - Auto-generate shopping lists based on what's running low

5. **User Preferences**
   - Store preferences (preferred proteins, cuisines)
   - Learn from past meal plan ratings

## Testing

### Test Coverage

```python
# Test meal plan generation
test_generate_meal_plan_with_criteria()
test_generate_meal_plan_respects_variety()
test_generate_shopping_list_aggregates_correctly()

# Test optimization
test_nutrition_balance_suggestions()
test_variety_checks()

# Test API endpoints
test_quick_generate_endpoint()
test_bulk_assign_endpoint()

# Test shopping list
test_mark_item_purchased()
test_mark_shopping_list_purchased()
```

## API Examples

### cURL

```bash
# Generate meal plan
curl -X POST http://localhost:8000/api/meal-plans/generate_quick/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{"name":"Weekly Plan","days":7}'

# Generate shopping list
curl -X POST http://localhost:8000/api/meal-plans/1/generate_shopping_list/ \
  -H "Authorization: Token YOUR_TOKEN"

# Mark items purchased
curl -X POST http://localhost:8000/api/shopping-lists/1/mark_purchased/ \
  -H "Authorization: Token YOUR_TOKEN"
```

### Python

```python
import requests

headers = {'Authorization': 'Token YOUR_TOKEN'}

# Quick generate
response = requests.post(
    'http://localhost:8000/api/meal-plans/generate_quick/',
    json={'name': 'Weekly Plan', 'days': 7},
    headers=headers
)
meal_plan = response.json()

# Generate shopping list
response = requests.post(
    f'http://localhost:8000/api/meal-plans/{meal_plan["id"]}/generate_shopping_list/',
    headers=headers
)
shopping_list = response.json()
```

## Support & Documentation

For additional help:
- Django admin: `/admin/larder/`
- API browsable interface: `/api/`
- Model documentation: See model docstrings
- Service documentation: See meal_planning_service.py

