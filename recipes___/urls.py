from django.urls import path

from . import views

app_name = 'recipes'

urlpatterns = [
    path('', views.recipe_dashboard, name='recipe_dashboard'),
    path('list/', views.recipe_list, name='recipe_list'),
    path('create/', views.recipe_create, name='recipe_create'),
    path('scrape/', views.scrape_recipe, name='scrape_recipe'),
    path('import-text/', views.import_from_text, name='import_from_text'),
    path('<int:pk>/', views.recipe_detail, name='recipe_detail'),
    path('<int:pk>/update/', views.recipe_update, name='recipe_update'),
    path('market/', views.market_explorer, name='market_explorer'),
    path('market/sources/', views.market_sources, name='market_sources'),
    path('market/sources/add/', views.market_source_add, name='market_source_add'),
    path('market/sources/<int:pk>/edit/', views.market_source_edit, name='market_source_edit'),
    path('market/sources/<int:pk>/delete/', views.market_source_delete, name='market_source_delete'),
    path('market/sources/<int:pk>/scrape/', views.market_source_scrape, name='market_source_scrape'),
    path('link-to-market/<int:ingredient_id>/', views.link_ingredient_to_market, name='link_to_market'),
    path('shopping-list/', views.shopping_list, name='shopping_list'),
    path('stock-purchased/', views.stock_purchased_ingredients, name='stock_purchased'),

    # Dietary Preferences
    path('preferences/', views.preferences, name='preferences'),

    # Larder
    path('larder/', views.larder_dashboard, name='larder_dashboard'),
    path('larder/add/', views.larder_add, name='larder_add'),
    path('larder/<int:pk>/edit/', views.larder_edit, name='larder_edit'),
    path('larder/<int:pk>/delete/', views.larder_delete, name='larder_delete'),
    path('larder/<int:pk>/consume/', views.larder_consume, name='larder_consume'),
    path('larder/cook/', views.larder_cook, name='larder_cook'),

    # Meal Plans
    path('meal-plans/', views.meal_plan_list, name='meal_plan_list'),
    path('meal-plan/generate/', views.meal_plan_generate, name='meal_plan_generate'),
    path('meal-plan/<int:pk>/', views.meal_plan_detail, name='meal_plan_detail'),
    path('meal-plan/<int:pk>/delete/', views.meal_plan_delete, name='meal_plan_delete'),
    path('meal-plan/<int:plan_id>/day/<int:day_id>/swap/', views.meal_plan_swap, name='meal_plan_swap'),
    path('meal-plan/<int:plan_id>/shopping-list/', views.meal_plan_shopping_list, name='meal_plan_shopping_list'),
    path('meal-plan/<int:plan_id>/shopping-list/item/<int:item_id>/purchased/', views.shopping_list_item_purchased, name='shopping_list_item_purchased'),
]
