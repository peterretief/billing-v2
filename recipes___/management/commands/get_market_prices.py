import os
import json
import re
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.conf import settings
from google import genai
from firecrawl import FirecrawlApp
from recipes.models import MarketPrice, Ingredient

class Command(BaseCommand):
    help = "Scrapes CT Market and performs a High-Precision Global Price Sync"

    def handle(self, *args, **options):
        # 1. Initialize Clients
        firecrawl = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        
        self.stdout.write(self.style.SUCCESS("Step 1: Scraping CT Market (Large Batch)..."))
        
        # 2. Scrape (CSV click results in large markdown block)
        markdown_data = ""
        try:
            scrape_result = firecrawl.scrape(
                
                url='https://www.ctmarket.co.za/daily-prices/',
                formats=['markdown'],
                only_main_content=False,
                actions=[
                    {"type": "wait", "milliseconds": 5000},
                    {"type": "click", "selector": ".buttons-csv"}, 
                    {"type": "wait", "milliseconds": 15000}
                ]
            )
            
            if hasattr(scrape_result, 'markdown'):
                markdown_data = scrape_result.markdown
            elif isinstance(scrape_result, dict):
                markdown_data = scrape_result.get('markdown', '')

            self.stdout.write(f"Received {len(markdown_data)} characters of data.")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Scrape Error: {str(e)}"))
            return

        # 3. Batch Parsing to avoid LLM truncation
        self.stdout.write(self.style.SUCCESS("Step 2: AI Parsing Catalog in Batches..."))
        
        lines = markdown_data.split('\n')
        batch_size = 80 # Lines per batch
        all_market_items = []

        for i in range(0, len(lines), batch_size):
            batch_text = "\n".join(lines[i:i+batch_size])
            if len(batch_text.strip()) < 50: continue
            
            self.stdout.write(f"  Parsing batch {int(i/batch_size) + 1}...")
            
            prompt = (
                "Extract produce items from this data chunk into a JSON array of objects. "
                "\nRules: "
                "- sku_key: ShortCode + Variety + Mass + Grade (e.g., 'APBB ECONO 3kg 1S'). "
                "- Commodity: Full Name. "
                "- Variety: Variety name. "
                "- Weight: Numeric mass in kg. "
                "- Class Size: The Grade/Size code. "
                "- Total Price: The AVERAGE PRICE (final decimal). "
                "\nReturn ONLY a JSON array: [{'sku_key': '...', 'commodity': '...', 'variety': '...', 'weight': 0.0, 'class_size': '...', 'total_price': 0.00}] "
                f"\n\nDATA CHUNK:\n{batch_text}"
            )

            try:
                response = client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
                batch_items = json.loads(response.text.strip())
                if isinstance(batch_items, list):
                    all_market_items.extend(batch_items)
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"    Batch Error: {str(e)}"))

        # 4. Sync
        self.stdout.write(self.style.SUCCESS(f"Step 3: Syncing {len(all_market_items)} items..."))
        
        updated_skus = 0
        for item in all_market_items:
            try:
                sku = item.get('sku_key')
                if not sku: continue
                price = Decimal(str(item.get('total_price', '0.00')))
                weight = Decimal(str(item.get('weight', '0.000')))
                
                market_obj, created = MarketPrice.objects.update_or_create(
                    sku_key=sku,
                    defaults={
                        'commodity': item['commodity'],
                        'variety': item['variety'],
                        'weight': weight,
                        'class_size': item.get('class_size', 'N/A'),
                        'total_price': price,
                    }
                )
                Ingredient.objects.filter(market_ref=market_obj).update(purchase_value=price)
                updated_skus += 1
            except:
                continue

        self.stdout.write(self.style.SUCCESS(f"--- Sync Complete: {updated_skus} SKUs Processed ---"))
