import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import TenantModel


# ---------------------------------------------------------------------------
# Price Sources (supplier scraper registry, global)
# ---------------------------------------------------------------------------

class PriceSource(models.Model):
    """A configured URL that can be scraped to update the MarketPrice catalog."""
    name = models.CharField(max_length=255, unique=True)
    url = models.URLField()
    notes = models.TextField(
        blank=True,
        help_text="Optional hints for the AI parser (e.g. 'prices in ZAR per kg, table format').",
    )
    is_active = models.BooleanField(default=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    last_item_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def slug(self):
        """Short prefix used to namespace sku_keys for this source."""
        return self.name[:12].replace(" ", "_").lower()

    @property
    def status(self):
        if self.last_error:
            return "error"
        if self.last_scraped:
            return "ok"
        return "new"


# ---------------------------------------------------------------------------
# Global Price Catalog (non-tenant)
# ---------------------------------------------------------------------------

class MarketPrice(models.Model):
    """Global Master Catalog - No Tenant ID"""
    sku_key = models.CharField(max_length=100, unique=True)
    commodity = models.CharField(max_length=100)
    variety = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=10, decimal_places=3)
    class_size = models.CharField(max_length=20, default="N/A")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.ForeignKey(
        PriceSource,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="prices",
    )
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.commodity} ({self.sku_key})"

    @property
    def store_name(self):
        """Best-effort store name from SKU key prefix (e.g. 'woolworths_apple' → 'Woolworths')."""
        return self.sku_key.split("_")[0].title() if "_" in self.sku_key else self.sku_key.title()

    @property
    def price_per_kg(self):
        if self.weight > 0:
            return self.total_price / self.weight
        return self.total_price


# ---------------------------------------------------------------------------
# Recipe Tags (global, non-tenant)
# ---------------------------------------------------------------------------

class RecipeTag(models.Model):
    """Predefined dietary/style tags for recipes."""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Ingredient (tenant-specific)
# ---------------------------------------------------------------------------

class Ingredient(TenantModel):
    """Tenant-Specific Ingredient with optional market price link."""
    name = models.CharField(max_length=255)
    market_ref = models.ForeignKey(
        MarketPrice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # Link to physical inventory for procurement
    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recipe_ingredients",
    )
    purchase_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    purchase_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.000)
    unit = models.CharField(max_length=50, default="kg")

    # Dietary flags — set by scraper or manually
    is_vegetarian = models.BooleanField(default=True)
    is_vegan = models.BooleanField(default=True)
    is_halal = models.BooleanField(default=True)
    is_gluten_free = models.BooleanField(default=True)
    is_dairy_free = models.BooleanField(default=True)
    is_nut_free = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    @property
    def price_per_unit(self):
        if self.purchase_quantity > 0:
            return self.purchase_value / self.purchase_quantity
        return Decimal("0")


# ---------------------------------------------------------------------------
# Recipe (tenant-specific)
# ---------------------------------------------------------------------------

MEAL_TYPE_CHOICES = [
    ("breakfast", "Breakfast"),
    ("lunch", "Lunch"),
    ("dinner", "Dinner"),
    ("snack", "Snack"),
    ("any", "Any Meal"),
]


class Recipe(TenantModel):
    """Tier 2: The Instruction Set"""
    name = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    servings_yield = models.PositiveIntegerField(default=1)

    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES, default="any")
    tags = models.ManyToManyField(RecipeTag, blank=True, related_name="recipes")

    # Explicit dietary flags (set when importing/scraping, or via recompute_dietary_flags)
    is_vegetarian = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    is_halal = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    is_dairy_free = models.BooleanField(default=False)
    is_nut_free = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @property
    def total_cost(self):
        """Calculates total cost based on current ingredient prices."""
        return sum(c.component_cost for c in self.components.all())

    @property
    def cost_per_serving(self):
        """Calculates cost per person."""
        if self.servings_yield > 0:
            return self.total_cost / self.servings_yield
        return 0

    def recompute_dietary_flags(self):
        """
        Derive dietary flags from ingredient flags and persist them.
        Call this after adding/removing components.
        """
        components = list(self.components.select_related("ingredient").all())
        if not components:
            return
        self.is_vegetarian = all(c.ingredient.is_vegetarian for c in components)
        self.is_vegan = all(c.ingredient.is_vegan for c in components)
        self.is_halal = all(c.ingredient.is_halal for c in components)
        self.is_gluten_free = all(c.ingredient.is_gluten_free for c in components)
        self.is_dairy_free = all(c.ingredient.is_dairy_free for c in components)
        self.is_nut_free = all(c.ingredient.is_nut_free for c in components)
        self.save(update_fields=[
            "is_vegetarian", "is_vegan", "is_halal",
            "is_gluten_free", "is_dairy_free", "is_nut_free",
        ])


# ---------------------------------------------------------------------------
# Recipe Component (join table)
# ---------------------------------------------------------------------------

class RecipeComponent(TenantModel):
    """The 'Join': Links Recipe to Ingredient with Quantity"""
    recipe = models.ForeignKey(Recipe, related_name="components", on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    quantity_used = models.DecimalField(max_digits=10, decimal_places=3)

    @property
    def component_cost(self):
        """(Market Price / Bulk Qty) * Amount Used"""
        if self.ingredient.purchase_quantity > 0:
            return (self.ingredient.purchase_value / self.ingredient.purchase_quantity) * self.quantity_used
        return 0


# ---------------------------------------------------------------------------
# Menu (tenant-specific)
# ---------------------------------------------------------------------------

class Menu(TenantModel):
    """Tier 3: The Commander (Aggregator)"""
    title = models.CharField(max_length=255)
    recipes = models.ManyToManyField(Recipe, related_name="menus")

    def __str__(self):
        return self.title

    def generate_procurement_list(self, headcount):
        """The magic button for Market Agents."""
        summary = {}
        for recipe in self.recipes.all():
            factor = Decimal(str(headcount / recipe.servings_yield))
            for comp in recipe.components.all():
                name = comp.ingredient.name
                qty = comp.quantity_used * factor
                cost = comp.component_cost * factor
                if name not in summary:
                    summary[name] = {"qty": 0, "cost": 0, "unit": comp.ingredient.unit}
                summary[name]["qty"] += qty
                summary[name]["cost"] += cost
        return summary


# ---------------------------------------------------------------------------
# User Dietary Preferences (1:1 with User, non-tenant)
# ---------------------------------------------------------------------------

class UserPreference(models.Model):
    """Dietary preferences and serving size for meal plan generation."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipe_preference",
    )

    # Dietary filters
    is_vegetarian = models.BooleanField(default=False, verbose_name="Vegetarian")
    is_vegan = models.BooleanField(default=False, verbose_name="Vegan")
    is_halal = models.BooleanField(default=False, verbose_name="Halal")
    is_gluten_free = models.BooleanField(default=False, verbose_name="Gluten Free")
    is_dairy_free = models.BooleanField(default=False, verbose_name="Dairy Free")
    is_nut_free = models.BooleanField(default=False, verbose_name="Nut Free")

    servings = models.PositiveIntegerField(default=2, help_text="Number of people to cook for")
    preferred_cuisines = models.CharField(
        max_length=500, blank=True,
        help_text="Comma-separated list of preferred cuisines (e.g. Italian, Asian, Mediterranean)",
    )
    excluded_ingredients = models.ManyToManyField(
        Ingredient,
        blank=True,
        related_name="excluded_by_users",
        help_text="Specific ingredients to exclude from all meal plans",
    )

    def __str__(self):
        return f"Preferences for {self.user}"

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj

    @property
    def active_filters(self):
        labels = []
        for field in ("is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free"):
            if getattr(self, field):
                labels.append(self._meta.get_field(field).verbose_name)
        return labels


# ---------------------------------------------------------------------------
# Meal Plan
# ---------------------------------------------------------------------------

class MealPlan(TenantModel):
    """A date-range meal plan owned by a user."""
    title = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.title} ({self.start_date} → {self.end_date})"

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def total_estimated_cost(self):
        try:
            return sum(item.estimated_cost for item in self.shopping_list.items.all())
        except ShoppingList.DoesNotExist:
            return None


class MealPlanDay(models.Model):
    """One day within a MealPlan, with breakfast / lunch / dinner slots."""
    meal_plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name="days")
    date = models.DateField()
    breakfast = models.ForeignKey(
        Recipe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="breakfast_days",
    )
    lunch = models.ForeignKey(
        Recipe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="lunch_days",
    )
    dinner = models.ForeignKey(
        Recipe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dinner_days",
    )

    class Meta:
        ordering = ["date"]
        unique_together = ("meal_plan", "date")

    def __str__(self):
        return f"{self.meal_plan.title} — {self.date}"

    def set_meal(self, slot, recipe):
        if slot not in ("breakfast", "lunch", "dinner"):
            raise ValueError(f"Invalid meal slot: {slot}")
        setattr(self, slot, recipe)
        self.save(update_fields=[slot])


# ---------------------------------------------------------------------------
# Shopping List
# ---------------------------------------------------------------------------

class ShoppingList(TenantModel):
    """Aggregated ingredient list for a MealPlan, grouped by store."""
    meal_plan = models.OneToOneField(
        MealPlan, on_delete=models.CASCADE, related_name="shopping_list",
    )
    generated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Shopping list for {self.meal_plan}"

    @property
    def total_cost(self):
        """What still needs to be purchased (shortfall cost only)."""
        return sum(item.estimated_cost for item in self.items.all())

    @property
    def larder_savings(self):
        """Value of ingredients already stocked — money you don't need to spend."""
        return sum(item.larder_value for item in self.items.all())

    @property
    def total_plan_cost(self):
        """Full cost of the meal plan at current prices (purchase + larder value)."""
        return self.total_cost + self.larder_savings

    @property
    def items_by_store(self):
        grouped = {}
        for item in self.items.select_related("ingredient", "ingredient__market_ref").order_by(
            "store_source", "ingredient__name"
        ):
            store = item.store_source or "General"
            grouped.setdefault(store, []).append(item)
        return grouped

    @property
    def cost_by_store(self):
        return {store: sum(i.estimated_cost for i in items) for store, items in self.items_by_store.items()}


class ShoppingListItem(models.Model):
    """
    One aggregated ingredient line on a shopping list.

    Quantities and costs are split into two buckets:
      • quantity_in_larder / larder_value  — already stocked, no spend needed
      • quantity_to_buy  / estimated_cost  — shortfall, needs to be purchased
    """
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)

    total_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=50)

    # Larder stock that covers part (or all) of the need
    quantity_in_larder = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    larder_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Cost-equivalent of the quantity already stocked in the larder.",
    )

    # What still needs to be purchased
    quantity_to_buy = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    estimated_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Cost to purchase the shortfall (total minus larder stock).",
    )

    store_source = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["store_source", "ingredient__name"]

    def __str__(self):
        return f"{self.ingredient.name} × {self.total_quantity} {self.unit}"

    @property
    def is_fully_covered(self):
        return self.quantity_to_buy == 0

    @property
    def is_partially_covered(self):
        return Decimal("0") < self.quantity_in_larder < self.total_quantity


# ---------------------------------------------------------------------------
# Meal Plan Generation Helpers
# ---------------------------------------------------------------------------

def _filtered_recipes(user, preference, meal_type):
    """Return recipes matching the user's dietary preferences for the given meal type."""
    if meal_type == "any":
        qs = Recipe.objects.filter(user=user)
    else:
        qs = Recipe.objects.filter(user=user, meal_type__in=[meal_type, "any"])

    if preference.is_vegetarian:
        qs = qs.filter(is_vegetarian=True)
    if preference.is_vegan:
        qs = qs.filter(is_vegan=True)
    if preference.is_halal:
        qs = qs.filter(is_halal=True)
    if preference.is_gluten_free:
        qs = qs.filter(is_gluten_free=True)
    if preference.is_dairy_free:
        qs = qs.filter(is_dairy_free=True)
    if preference.is_nut_free:
        qs = qs.filter(is_nut_free=True)

    excluded_ids = list(preference.excluded_ingredients.values_list("id", flat=True))
    if excluded_ids:
        qs = qs.exclude(components__ingredient__in=excluded_ids)

    return qs.distinct()


def generate_meal_plan(user, title, start_date, end_date):
    """
    Auto-generate a MealPlan for the given user and date range.
    Respects UserPreference; avoids repeating recipes within the same week.
    """
    preference = UserPreference.for_user(user)

    breakfast_pool = list(_filtered_recipes(user, preference, "breakfast"))
    lunch_pool = list(_filtered_recipes(user, preference, "lunch"))
    dinner_pool = list(_filtered_recipes(user, preference, "dinner"))

    meal_plan = MealPlan.objects.create(
        user=user, title=title, start_date=start_date, end_date=end_date,
    )

    current = start_date
    week_start = start_date
    used: dict = {"breakfast": set(), "lunch": set(), "dinner": set()}

    def pick(pool, used_set):
        available = [r for r in pool if r.pk not in used_set]
        if not available:
            available = pool  # Wrap around when pool exhausted
        if not available:
            return None
        choice = random.choice(available)
        used_set.add(choice.pk)
        return choice

    while current <= end_date:
        if (current - week_start).days >= 7:
            used = {"breakfast": set(), "lunch": set(), "dinner": set()}
            week_start = current

        MealPlanDay.objects.create(
            meal_plan=meal_plan,
            date=current,
            breakfast=pick(breakfast_pool, used["breakfast"]),
            lunch=pick(lunch_pool, used["lunch"]),
            dinner=pick(dinner_pool, used["dinner"]),
        )
        current += timedelta(days=1)

    return meal_plan


def generate_shopping_list(meal_plan):
    """
    Build (or rebuild) the larder-aware ShoppingList for a MealPlan.

    For each ingredient the plan needs:
      1. Total quantity needed  = sum(quantity_used × serving_scale) across all days/meals
      2. Quantity in larder     = how much is already stocked (via LarderItem.ingredient FK)
      3. Quantity to buy        = max(0, needed − in_larder)
      4. estimated_cost         = (quantity_to_buy / purchase_quantity) × purchase_value
      5. larder_value           = cost equivalent of the stock already on hand

    This means a meal plan's shopping list only costs what you still need to purchase;
    ingredients already in the larder are shown as "covered" with their imputed value.
    """
    ShoppingList.objects.filter(meal_plan=meal_plan).delete()
    shopping_list = ShoppingList.objects.create(user=meal_plan.user, meal_plan=meal_plan)

    try:
        servings = meal_plan.user.recipe_preference.servings
    except UserPreference.DoesNotExist:
        servings = 1

    # --- Step 1: aggregate total quantity needed per ingredient ---
    needs: dict = {}

    for day in meal_plan.days.prefetch_related(
        "breakfast__components__ingredient__market_ref",
        "lunch__components__ingredient__market_ref",
        "dinner__components__ingredient__market_ref",
    ):
        for recipe in filter(None, [day.breakfast, day.lunch, day.dinner]):
            scale = (
                Decimal(str(servings)) / Decimal(str(recipe.servings_yield))
                if recipe.servings_yield > 0 else Decimal("1")
            )
            for comp in recipe.components.all():
                ing = comp.ingredient
                if ing.pk not in needs:
                    needs[ing.pk] = {
                        "ingredient": ing,
                        "qty": Decimal("0"),
                        "unit": ing.unit,
                        "store": ing.market_ref.store_name if ing.market_ref else "",
                    }
                needs[ing.pk]["qty"] += comp.quantity_used * scale

    # --- Step 2: build larder stock map (ingredient_id → total qty available) ---
    larder_stock: dict = {}
    for larder_item in LarderItem.objects.filter(
        user=meal_plan.user,
        ingredient__isnull=False,
        ingredient_id__in=list(needs.keys()),
    ):
        iid = larder_item.ingredient_id
        larder_stock[iid] = larder_stock.get(iid, Decimal("0")) + larder_item.quantity

    # --- Step 3: calculate shortfall and costs, then bulk-create items ---
    items_to_create = []

    for ing_id, data in needs.items():
        ing = data["ingredient"]
        qty_needed = data["qty"].quantize(Decimal("0.001"))

        # How much the larder covers (capped at qty_needed)
        qty_in_larder = min(
            larder_stock.get(ing_id, Decimal("0")),
            qty_needed,
        ).quantize(Decimal("0.001"))

        qty_to_buy = max(Decimal("0"), qty_needed - qty_in_larder).quantize(Decimal("0.001"))

        # Cost per unit from ingredient catalog: purchase_value / purchase_quantity
        if ing.purchase_quantity > 0:
            cpu = ing.purchase_value / ing.purchase_quantity
            purchase_cost = (cpu * qty_to_buy).quantize(Decimal("0.01"))
            larder_value = (cpu * qty_in_larder).quantize(Decimal("0.01"))
        else:
            purchase_cost = Decimal("0")
            larder_value = Decimal("0")

        items_to_create.append(ShoppingListItem(
            shopping_list=shopping_list,
            ingredient=ing,
            total_quantity=qty_needed,
            unit=data["unit"],
            quantity_in_larder=qty_in_larder,
            quantity_to_buy=qty_to_buy,
            estimated_cost=purchase_cost,
            larder_value=larder_value,
            store_source=data["store"],
        ))

    ShoppingListItem.objects.bulk_create(items_to_create)
    return shopping_list


# ---------------------------------------------------------------------------
# Larder (Pantry)
# ---------------------------------------------------------------------------

class LarderItem(TenantModel):
    """
    A physical ingredient currently sitting in the user's larder/pantry.
    Tracks quantity, expiry date, and whether the item is a staple.
    """
    ingredient = models.ForeignKey(
        Ingredient,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="larder_items",
        help_text="Link to your ingredient catalog (optional — enables cost tracking).",
    )
    name = models.CharField(max_length=255, help_text="Display name of the item.")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("1.000"))
    unit = models.CharField(max_length=50, default="units")
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text="Leave blank for items without a meaningful expiry (e.g. dried pasta).",
    )
    is_staple = models.BooleanField(
        default=False,
        help_text="Staples (salt, oil, flour) are always assumed available and never trigger expiry alerts.",
    )
    cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Used to prioritise expensive items (meat, dairy) when they near expiry.",
    )
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        # Non-staples first, soonest-expiring first, then alpha by name
        ordering = ["is_staple", "expiry_date", "name"]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    # ------------------------------------------------------------------
    # Expiry helpers
    # ------------------------------------------------------------------

    @property
    def days_until_expiry(self):
        if self.expiry_date is None:
            return None
        from django.utils import timezone
        return (self.expiry_date - timezone.localdate()).days

    @property
    def is_expired(self):
        d = self.days_until_expiry
        return d is not None and d < 0

    @property
    def is_expiring_soon(self):
        """True when the item expires within 48 hours (days ≤ 2)."""
        d = self.days_until_expiry
        return d is not None and 0 <= d <= 2

    @property
    def urgency(self):
        """
        Returns one of: 'expired' | 'critical' | 'warning' | 'ok' | 'staple'.
        Used for colour-coding in templates.
        """
        if self.is_staple:
            return "staple"
        d = self.days_until_expiry
        if d is None:
            return "ok"
        if d < 0:
            return "expired"
        if d <= 2:
            return "critical"
        if d <= 7:
            return "warning"
        return "ok"

    @property
    def total_value(self):
        return self.cost_per_unit * self.quantity

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def consume(self, qty_used):
        """
        Reduce quantity by qty_used (Decimal or float).
        Deletes the item if quantity reaches zero.
        Returns True if item was deleted.
        """
        self.quantity = max(Decimal("0"), self.quantity - Decimal(str(qty_used)))
        if self.quantity == 0:
            self.delete()
            return True
        self.save(update_fields=["quantity"])
        return False


# ---------------------------------------------------------------------------
# Larder AI Prompt Builder
# ---------------------------------------------------------------------------

def build_larder_prompt(user):
    """
    Build a FIFO-prioritised AI prompt from the user's current larder.

    Priority ordering:
        1. Expired / ≤ 48 h  → "Must Use"
        2. High-cost items expiring within 7 days  → "Prioritise"
        3. Everything else (not staple)  → "Available in Larder"
        4. Staples  → "Staples"

    Returns (system_prompt: str, user_prompt: str, has_must_use: bool).
    """
    items = LarderItem.objects.filter(user=user).order_by("is_staple", "expiry_date", "-cost_per_unit", "name")

    must_use: list = []
    high_value: list = []
    available: list = []
    staples: list = []

    for item in items:
        if item.is_staple:
            staples.append(item)
            continue
        d = item.days_until_expiry
        if d is not None and d <= 2:
            must_use.append(item)
        elif d is not None and d <= 7 and item.cost_per_unit > 0:
            high_value.append(item)
        else:
            available.append(item)

    def _fmt(item):
        d = item.days_until_expiry
        if d is None:
            return f"{item.name} ({item.quantity} {item.unit})"
        if d < 0:
            suffix = "EXPIRED"
        elif d == 0:
            suffix = "expires today"
        elif d == 1:
            suffix = "expires tomorrow"
        else:
            suffix = f"expires in {d} day{'s' if d != 1 else ''}"
        return f"{item.name} ({item.quantity} {item.unit}, {suffix})"

    sections = []
    if must_use:
        sections.append(
            "Must Use (Expiring Soon):\n" + "\n".join(f"  - {_fmt(i)}" for i in must_use)
        )
    if high_value:
        sections.append(
            "Prioritise (Expensive, Expiring This Week):\n" + "\n".join(f"  - {_fmt(i)}" for i in high_value)
        )
    if available:
        sections.append(
            "Available in Larder:\n" + "\n".join(f"  - {_fmt(i)}" for i in available)
        )
    if staples:
        sections.append(
            "Staples (always on hand): " + ", ".join(i.name for i in staples)
        )

    user_prompt = "\n\n".join(sections)
    user_prompt += (
        "\n\nTask: Generate a single recipe that:\n"
        "1. Uses ALL 'Must Use' items.\n"
        "2. Incorporates 'Prioritise' items wherever possible.\n"
        "3. Minimises the cost of any ingredients NOT in the larder.\n"
        "4. Is nutritionally balanced.\n\n"
        "Return a single JSON object with keys:\n"
        "  name (string), servings (integer), instructions (string),\n"
        "  ingredients (list of {name, qty, unit, from_larder (bool)})."
    )

    system_prompt = (
        "You are a cost-conscious, health-focused chef. "
        "Your primary goal is to eliminate food waste by using expiring ingredients first. "
        "Generate practical, delicious recipes from whatever is available."
    )

    return system_prompt, user_prompt, bool(must_use)
