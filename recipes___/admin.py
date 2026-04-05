from django.contrib import admin

from .models import (
    Ingredient,
    LarderItem,
    MarketPrice,
    MealPlan,
    MealPlanDay,
    Menu,
    PriceSource,
    Recipe,
    RecipeComponent,
    RecipeTag,
    ShoppingList,
    ShoppingListItem,
    UserPreference,
)


@admin.register(PriceSource)
class PriceSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "is_active", "last_scraped", "last_item_count", "status_display")
    search_fields = ("name", "url")
    list_filter = ("is_active",)
    readonly_fields = ("last_scraped", "last_item_count", "last_error", "created_at")

    @admin.display(description="Status")
    def status_display(self, obj):
        icons = {"ok": "✅", "error": "❌", "new": "⏳"}
        return f"{icons.get(obj.status, '')} {obj.status.title()}"


@admin.register(MarketPrice)
class MarketPriceAdmin(admin.ModelAdmin):
    list_display = ("commodity", "variety", "sku_key", "weight", "total_price", "source", "last_updated")
    search_fields = ("commodity", "variety", "sku_key")
    list_filter = ("commodity", "source")
    ordering = ("commodity", "variety")


@admin.register(RecipeTag)
class RecipeTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class RecipeComponentInline(admin.TabularInline):
    model = RecipeComponent
    extra = 1
    fields = ("ingredient", "quantity_used")


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = (
        "name", "unit", "purchase_value", "purchase_quantity", "calories_per_unit",
        "is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free",
        "user",
    )
    search_fields = ("name",)
    list_filter = ("is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free", "user")
    list_editable = ("calories_per_unit", "is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = (
        "name", "meal_type", "servings_yield",
        "is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free",
        "user",
    )
    search_fields = ("name",)
    list_filter = (
        "meal_type", "is_vegetarian", "is_vegan", "is_halal",
        "is_gluten_free", "is_dairy_free", "is_nut_free", "tags", "user",
    )
    filter_horizontal = ("tags",)
    inlines = [RecipeComponentInline]
    actions = ["recompute_dietary_flags"]

    @admin.action(description="Recompute dietary flags from ingredients")
    def recompute_dietary_flags(self, request, queryset):
        for recipe in queryset:
            recipe.recompute_dietary_flags()
        self.message_user(request, f"Recomputed dietary flags for {queryset.count()} recipe(s).")


@admin.register(RecipeComponent)
class RecipeComponentAdmin(admin.ModelAdmin):
    list_display = ("recipe", "ingredient", "quantity_used", "user")
    search_fields = ("recipe__name", "ingredient__name")
    list_filter = ("user",)


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ("title", "user")
    search_fields = ("title",)
    list_filter = ("user",)
    filter_horizontal = ("recipes",)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user", "servings",
        "is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free",
    )
    search_fields = ("user__email", "user__username")
    list_filter = ("is_vegetarian", "is_vegan", "is_halal", "is_gluten_free", "is_dairy_free", "is_nut_free")
    filter_horizontal = ("excluded_ingredients",)


class MealPlanDayInline(admin.TabularInline):
    model = MealPlanDay
    extra = 0
    fields = ("date", "breakfast", "lunch", "dinner")


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "end_date", "total_days_display", "user")
    search_fields = ("title",)
    list_filter = ("user", "start_date")
    inlines = [MealPlanDayInline]

    @admin.display(description="Days")
    def total_days_display(self, obj):
        return obj.total_days


class ShoppingListItemInline(admin.TabularInline):
    model = ShoppingListItem
    extra = 0
    fields = ("ingredient", "total_quantity", "unit", "estimated_cost", "store_source")
    readonly_fields = ("estimated_cost",)


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ("meal_plan", "total_cost_display", "generated_at", "user")
    search_fields = ("meal_plan__title",)
    list_filter = ("user",)
    inlines = [ShoppingListItemInline]
    readonly_fields = ("generated_at",)

    @admin.display(description="Total Cost")
    def total_cost_display(self, obj):
        return f"R {obj.total_cost:.2f}"


@admin.register(LarderItem)
class LarderItemAdmin(admin.ModelAdmin):
    list_display = (
        "name", "quantity", "unit", "expiry_date", "urgency_display",
        "is_staple", "cost_per_unit", "total_value_display", "user",
    )
    search_fields = ("name", "notes")
    list_filter = ("is_staple", "user", "expiry_date")
    list_editable = ("quantity", "is_staple")
    readonly_fields = ("urgency_display", "total_value_display", "days_until_expiry_display")
    ordering = ("is_staple", "expiry_date", "name")

    @admin.display(description="Urgency")
    def urgency_display(self, obj):
        icons = {"expired": "💀", "critical": "🔴", "warning": "🟡", "ok": "🟢", "staple": "⭐"}
        return f"{icons.get(obj.urgency, '')} {obj.urgency.title()}"

    @admin.display(description="Total Value")
    def total_value_display(self, obj):
        return f"R {obj.total_value:.2f}"

    @admin.display(description="Days Until Expiry")
    def days_until_expiry_display(self, obj):
        d = obj.days_until_expiry
        return "No expiry" if d is None else f"{d} day{'s' if d != 1 else ''}"
