import openfoodfacts
from .models import ProductMaster

def get_or_create_global_product(barcode):
    barcode = str(barcode).strip()

    # 1. Check local cache first
    product = ProductMaster.objects.filter(barcode=barcode).first()
    if product:
        return product, False

    # 2. Query OpenFoodFacts
    try:
        api = openfoodfacts.API(user_agent="PeterBillingApp/1.0")
        result = api.product.get(barcode)
    except Exception as e:
        print(f"OpenFoodFacts API error for barcode {barcode}: {e}")
        return None, False

    # 3. Validation - Ensure the API actually gave us data
    if not result:
        return None, False

    nutriments = result.get('nutriments', {})

    # 4. Save enriched product data
    new_product = ProductMaster.objects.create(
        barcode=barcode,
        name=result.get('product_name') or 'Unknown Item',
        brand=result.get('brands') or 'Generic',

        # Pull specific nutrients you care about, with safe fallbacks
        nutrition_data={
            'calories':       nutriments.get('energy-kcal_100g'),
            'protein':        nutriments.get('proteins_100g'),
            'carbohydrates':  nutriments.get('carbohydrates_100g'),
            'fat':            nutriments.get('fat_100g'),
            'fiber':          nutriments.get('fiber_100g'),
            'sugar':          nutriments.get('sugars_100g'),
            'sodium':         nutriments.get('sodium_100g'),
            'per':            '100g',
        },

        # Enrich metadata from OFF fields
        metadata={
            'source':        'Open Food Facts',
            'category':      result.get('categories_tags', []),
            'image_url':     result.get('image_front_url'),
            'ingredients':   result.get('ingredients_text'),
            'nutriscore':    result.get('nutriscore_grade'),
            'nova_group':    result.get('nova_group'),       # 1=unprocessed, 4=ultra-processed
            'labels':        result.get('labels_tags', []),  # e.g. ['en:organic', 'en:gluten-free']
        },
    )
    return new_product, True