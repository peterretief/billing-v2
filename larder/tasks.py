from celery import shared_task
from celery.schedules import crontab
from celery.decorators import periodic_task
import logging
from datetime import date

from .models import FreshProduce, GroceryStore
from playwright.sync_api import sync_playwright, TimeoutError

logger = logging.getLogger(__name__)

# Base URL for CT Market
CT_MARKET_URL = "https://www.ctmarket.co.za/daily-prices/"

@periodic_task(
    run_every=(crontab(hour=6, minute=0)), # Run daily at 6:00 AM
    name="daily_ct_market_produce_update",
    ignore_result=True,
)
def update_ct_market_produce():
    """
    Scrapes fresh produce data from CT Market and updates the FreshProduce model.
    This task runs daily and overwrites existing data with the latest prices.
    Handles dynamic data loading via pagination/load more buttons.
    """
    logger.info("Starting daily CT Market fresh produce scrape...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Run in headless mode
            page = browser.new_page()
            page.goto(CT_MARKET_URL)
            
            # Wait for the initial table to load - adjust selector if needed
            try:
                page.wait_for_selector("table.daily-prices-table", timeout=15000) # Increased timeout
            except TimeoutError:
                logger.error("Initial price table did not load within timeout.")
                browser.close()
                return

            ct_market_store = GroceryStore.objects.get(name="CT Market")
            all_produce_entries = [] # To store all scraped produce

            # --- Handle Pagination / Load More ---
            # This is a common pattern. You'll need to inspect CT Market's page 
            # to find the correct selector for the "Load More" or "Next Page" button.
            # Example placeholder selector:
            load_more_button_selector = "button.load-more-btn, a.pagination-next" 
            
            while True:
                try:
                    # Find all rows currently on the page
                    current_rows = page.query_selector_all("table.daily-prices-table tbody tr")
                    all_produce_entries.extend(current_rows)

                    # Try to find and click the load more button
                    # Use page.locator() for more robust handling
                    load_more_button = page.locator(load_more_button_selector).first
                    
                    # Check if the button is visible and enabled
                    if load_more_button.is_visible() and load_more_button.is_enabled():
                        logger.info("Found and clicking 'Load More' button...")
                        load_more_button.click()
                        page.wait_for_load_state('networkidle', timeout=10000) # Wait for network to be idle after click
                    else:
                        logger.info("No more 'Load More' button found or enabled. Exiting loop.")
                        break # Exit loop if button is not found or not interactable
                except TimeoutError:
                    logger.info("Timed out waiting for 'Load More' button or network idle. Assuming end of data.")
                    break
                except Exception as e:
                    logger.warning(f"Error interacting with load more button or waiting: {e}. Proceeding with current data.")
                    break # Exit loop on other errors

            # --- Process All Scraped Rows ---
            logger.info(f"Processing {len(all_produce_entries)} total produce entries.")
            for row in all_produce_entries:
                # Extract data from cells (td elements). Adjust selectors based on actual table structure.
                cells = row.query_selector_all("td")
                if len(cells) >= 4: # Ensure enough cells exist
                    name = cells[0].inner_text().strip()
                    category = cells[1].inner_text().strip() # Assuming category is second column
                    price_text = cells[2].inner_text().strip() # Assuming price is third column
                    unit_text = cells[3].inner_text().strip() # Assuming unit is fourth column

                    # --- Data Cleaning and Transformation ---
                    # Price cleaning (e.g., remove R, commas, convert to Decimal)
                    try:
                        # Example: "R 12.99" -> 12.99
                        price = float(price_text.replace('R', '').replace(',', '').strip())
                    except ValueError:
                        logger.warning(f"Could not parse price '{price_text}' for {name}")
                        continue # Skip this row if price is unparseable

                    # Unit parsing (e.g., "per kg", "per bunch") - needs specific logic
                    unit = "kg" # Default or attempt to parse
                    if "per kg" in unit_text.lower(): unit = "kg"
                    elif "per 100g" in unit_text.lower(): unit = "g" # Store as 'g' if per 100g
                    elif "per bunch" in unit_text.lower(): unit = "bunch"
                    elif "per unit" in unit_text.lower() or "each" in unit_text.lower(): unit = "unit"
                    # Add more unit parsing logic as needed

                    # --- Create/Update FreshProduce object ---
                    # Use update_or_create to ensure only current data is stored
                    # We might need to adjust unique_together or logic if category/supplier is not enough for uniqueness
                    obj, created = FreshProduce.objects.update_or_create(
                        name=name,
                        category=category,
                        supplier=ct_market_store,
                        unit=unit, # Store the parsed unit
                        defaults={
                            'price': price,
                            'last_refreshed_at': date.today(), # Or datetime.now()
                        }
                    )
                    if created:
                        logger.info(f"Created FreshProduce: {obj.name}")
                    else:
                        logger.debug(f"Updated FreshProduce: {obj.name}")

            browser.close()
            logger.info("CT Market fresh produce scrape completed successfully.")

    except Exception as e:
        logger.error(f"Error during CT Market fresh produce scrape: {e}", exc_info=True)

# Note: The periodic_task decorator handles scheduling.
# Make sure your Celery Beat is running and configured to discover tasks.
# You will need to inspect the CT Market website's HTML to find the correct selectors
# for the table, rows, and especially the 'load more' or pagination button.
# Example placeholder for button: "button.load-more-btn, a.pagination-next"
