"""
Simple JSON API for creating invoices from external systems (e.g., MealShare).
No Django REST Framework - uses standard Django views.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings

from clients.models import Client
from invoices.models import Invoice
from items.models import Item

User = get_user_model()

# API key for MealShare integration - set in Django settings
MEALSHARE_API_KEY = getattr(settings, "MEALSHARE_API_KEY", "change-me-in-settings")


@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def create_invoice_from_external(request):
    """
    Create line items (Items) from external system (MealShare).
    Items are then aggregated into invoices via billing_v2's normal invoicing process.
    
    POST /api/invoices/create/
    
    Expected JSON:
    {
        "api_key": "string",  # For authentication
        "client_external_id": "string",  # Links to Client.external_id
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "line_items": [
            {
                "description": "Meal name - date",
                "quantity": 1,
                "unit_price": "1234.56"
            }
        ]
    }
    """
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    # Validate API key
    api_key = data.get("api_key")
    if not api_key or api_key != MEALSHARE_API_KEY:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    # Validate required fields
    client_external_id = data.get("client_external_id")
    if not client_external_id:
        return JsonResponse({"error": "client_external_id is required"}, status=400)
    
    line_items = data.get("line_items", [])
    if not line_items:
        return JsonResponse({"error": "line_items cannot be empty"}, status=400)
    
    try:
        # Get or create client (assumes Client has an external_id field)
        client = Client.objects.get(external_id=client_external_id)
        user = client.user
    except Client.DoesNotExist:
        return JsonResponse(
            {"error": f"Client with external_id '{client_external_id}' not found"}, 
            status=404
        )
    
    # Calculate dates
    period_start = data.get("period_start", date.today().isoformat())
    period_end = data.get("period_end", date.today().isoformat())
    due_date_offset = data.get("due_date_offset_days", 30)
    
    try:
        period_start = date.fromisoformat(period_start)
        period_end = date.fromisoformat(period_end)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid date format (use YYYY-MM-DD)"}, status=400)
    
    due_date = date.today() + timedelta(days=due_date_offset)
    
    # Calculate totals
    subtotal = Decimal("0.00")
    for item in line_items:
        try:
            qty = Decimal(str(item.get("quantity", 1)))
            price = Decimal(str(item.get("unit_price", 0)))
            subtotal += qty * price
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Invalid quantity or unit_price in line items"}, 
                status=400
            )
    
    # Create line items (Items) - don't create invoice yet
    # The billing_v2 bulk invoicing process will aggregate these into invoices
    try:
        created_items = []
        for item_data in line_items:
            item = Item.objects.create(
                user=user,
                client=client,
                description=item_data.get("description", ""),
                quantity=Decimal(str(item_data.get("quantity", 1))),
                unit_price=Decimal(str(item_data.get("unit_price", 0))),
                date=date.today(),
            )
            created_items.append(item)
        
        return JsonResponse({
            "success": True,
            "message": "Line items created. Use billing_v2 bulk invoicing to create invoices.",
            "items_created": len(created_items),
            "total_amount": str(subtotal),
            "client_name": client.name,
            "client_id": client.id,
            "period_start": data.get("period_start"),
            "period_end": data.get("period_end"),
        }, status=201)
    
    except Exception as e:
        return JsonResponse(
            {"error": f"Failed to create line items: {str(e)}"}, 
            status=500
        )


@csrf_exempt
@require_http_methods(["GET"])
def get_invoice_pdf(request):
    """
    Get PDF of an invoice.
    
    GET /api/invoices/{invoice_id}/pdf/?api_key=...
    """
    
    api_key = request.GET.get("api_key")
    if not api_key or api_key != MEALSHARE_API_KEY:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    invoice_id = request.GET.get("invoice_id")
    if not invoice_id:
        return JsonResponse({"error": "invoice_id is required"}, status=400)
    
    try:
        # Import here to avoid circular imports
        from invoices.utils import generate_invoice_pdf
        from invoices.models import Invoice
        
        invoice = Invoice.objects.get(id=invoice_id)
        pdf_content = generate_invoice_pdf(invoice)
        
        response = JsonResponse({
            "success": True,
            "message": "Use the pdf_url endpoint to download"
        })
        return response
    except Invoice.DoesNotExist:
        return JsonResponse({"error": "Invoice not found"}, status=404)
    except Exception as e:
        return JsonResponse(
            {"error": f"Failed to generate PDF: {str(e)}"}, 
            status=500
        )
