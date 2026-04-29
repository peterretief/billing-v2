# MealShare Integration Guide

This document describes the REST API endpoints available for external systems (like MealShare) to create invoices in billing_v2.

## API Authentication

All API endpoints require an API key in the request. Set the API key in Django settings:

```python
# core_project/settings.py
MEALSHARE_API_KEY = "your-secret-api-key"
```

Or via environment variable:

```bash
# .env
MEALSHARE_API_KEY=your-secret-api-key
```

## Endpoints

### 1. Create Invoice from External System

**Endpoint:** `POST /invoices/api/create/`

**Purpose:** Create a new invoice from meal costs or other billing data.

**Authentication:** API key in request body

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "api_key": "your-secret-api-key",
  "client_external_id": "org-12345",
  "period_start": "2026-04-01",
  "period_end": "2026-04-30",
  "line_items": [
    {
      "description": "Chicken & Rice - Week 1 (30 portions)",
      "quantity": 1,
      "unit_price": "1234.56",
      "category": "Meals"
    },
    {
      "description": "Vegetarian Pasta - Week 1 (20 portions)",
      "quantity": 1,
      "unit_price": "856.40",
      "category": "Meals"
    }
  ],
  "send_email": false,
  "due_date_offset_days": 30
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | API key for authentication |
| client_external_id | string | Yes | External ID of the client/organisation to bill |
| period_start | string (YYYY-MM-DD) | No | Invoice period start date |
| period_end | string (YYYY-MM-DD) | No | Invoice period end date |
| line_items | array | Yes | Array of items to include in invoice |
| send_email | boolean | No | Send invoice email to client (default: false) |
| due_date_offset_days | integer | No | Days from today for due date (default: 30) |

**Line Item Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| description | string | Yes | Item description (e.g., meal name) |
| quantity | number | No | Quantity (default: 1) |
| unit_price | string | Yes | Price per unit (stored as Decimal for precision) |
| category | string | No | Item category (e.g., "Meals", "Delivery") |

**Response (201 Created):**
```json
{
  "success": true,
  "invoice_id": 42,
  "invoice_number": "INV-2026-000042",
  "total_amount": "2090.96",
  "status": "DRAFT",
  "client_name": "Test Organisation"
}
```

**Error Responses:**

```json
// 400 Bad Request - Invalid JSON
{"error": "Invalid JSON"}

// 400 Bad Request - Missing required field
{"error": "client_external_id is required"}
{"error": "line_items cannot be empty"}
{"error": "Invalid date format (use YYYY-MM-DD)"}
{"error": "Invalid quantity or unit_price in line items"}

// 401 Unauthorized - Invalid/missing API key
{"error": "Unauthorized"}

// 404 Not Found - Client doesn't exist
{"error": "Client with external_id 'org-12345' not found"}

// 500 Server Error
{"error": "Failed to create invoice: [error details]"}
```

### 2. Get Invoice PDF

**Endpoint:** `GET /invoices/api/pdf/`

**Purpose:** Get PDF of an existing invoice (returns metadata, actual PDF retrieval via separate endpoint).

**Parameters:**

| Parameter | Type | Required | In |
|-----------|------|----------|-----|
| api_key | string | Yes | query |
| invoice_id | integer | Yes | query |

**Example Request:**
```
GET /invoices/api/pdf/?api_key=your-secret-api-key&invoice_id=42
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Use the pdf_url endpoint to download"
}
```

**Error Responses:**

```json
// 400 Bad Request
{"error": "invoice_id is required"}

// 401 Unauthorized
{"error": "Unauthorized"}

// 404 Not Found
{"error": "Invoice not found"}

// 500 Server Error
{"error": "Failed to generate PDF: [error details]"}
```

## Integration Example (MealShare)

Here's how MealShare would integrate with these endpoints:

### 1. After weekly meal planning, aggregate costs:

```typescript
// app/api/organisations/[orgId]/invoices/generate/route.ts

export async function POST(request: Request, { params }: { params: { orgId: string } }) {
  const { period_start, period_end } = await request.json();
  
  // Query meals for the period
  const meals = await supabase
    .from('meals')
    .select('*, meal_ingredients(ingredient_id, qty_per_portion, ingredients(*))')
    .eq('organisation_id', orgId)
    .gte('meal_date', period_start)
    .lte('meal_date', period_end);
  
  // Calculate total cost per meal
  const lineItems = meals.map(meal => ({
    description: `${meal.name} (${meal.meal_ingredients.length} ingredients)`,
    quantity: 1,
    unit_price: meal.total_cost.toString(),
    category: 'Meals'
  }));
  
  // Call billing_v2 API
  const response = await fetch('http://billing_v2:8000/invoices/api/create/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: process.env.BILLING_V2_API_KEY,
      client_external_id: orgId,
      period_start,
      period_end,
      line_items: lineItems,
      send_email: false,
      due_date_offset_days: 30
    })
  });
  
  const invoice = await response.json();
  
  // Store invoice reference in MealShare
  if (invoice.success) {
    await supabase
      .from('invoice_references')
      .insert({
        organisation_id: orgId,
        billing_v2_invoice_id: invoice.invoice_id,
        total_amount: invoice.total_amount,
        period_start,
        period_end,
        created_at: new Date()
      });
  }
  
  return response;
}
```

### 2. Environment Configuration

Add to MealShare `.env`:

```env
# billing_v2 Integration
BILLING_V2_API_KEY=mealshare-dev-key-change-in-production
BILLING_V2_API_URL=http://localhost:8000/invoices/api/create/
BILLING_V2_CLIENT_EXTERNAL_ID_PREFIX=org_  # Or organisational identifier
```

Add to billing_v2 `.env`:

```env
MEALSHARE_API_KEY=mealshare-dev-key-change-in-production
```

## Database Requirements

The API requires these tables to exist:

- `clients` - Client records with `external_id` field
- `invoices` - Invoice records (status, dates, amounts)
- `items` - Line items for invoices

All requests are wrapped in `@transaction.atomic` to ensure data consistency.

## Notes

- All decimal amounts should be passed as strings to avoid float precision issues
- Invoice status starts as "DRAFT" - change manually in billing_v2 UI to "PENDING" when ready
- No tax calculation is performed by default - set `tax_amount = 0`
- Client must exist in billing_v2 database with matching `external_id`
- API key validation is case-sensitive

## Testing the API

```bash
# Create a test invoice
curl -X POST http://localhost:8000/invoices/api/create/ \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "mealshare-dev-key-change-in-production",
    "client_external_id": "test-org-1",
    "period_start": "2026-04-01",
    "period_end": "2026-04-30",
    "line_items": [
      {
        "description": "Test Meal",
        "quantity": 1,
        "unit_price": "100.00"
      }
    ]
  }'
```

Expected response:
```json
{
  "success": true,
  "invoice_id": 1,
  "invoice_number": "INV-2026-000001",
  "total_amount": "100.00",
  "status": "DRAFT",
  "client_name": "Test Organization"
}
```

## Future Enhancements

- [ ] Add API key management UI in Django admin
- [ ] Implement API key rotation
- [ ] Add rate limiting per API key
- [ ] Support batch invoice creation
- [ ] Add webhook for invoice status changes
- [ ] Implement invoice reconciliation API
