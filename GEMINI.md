# GEMINI.md - Billing V2 Instructional Context

This document provides a comprehensive overview of the **Billing V2** project, a production-ready Django billing and invoicing system. It serves as the primary instructional context for Gemini CLI interactions within this workspace.

## 🚀 Project Overview

**Billing V2** is a multi-tenant billing platform designed for service-based businesses. It automates recurring monthly invoices, tracks billable hours via timesheets, manages clients, and provides financial analytics.

### Core Technologies
- **Framework:** Django (Python 3.12+)
- **Asynchronous Tasks:** Celery + Redis
- **Database:** PostgreSQL
- **Real-time:** Django Channels + Daphne (WebSockets)
- **Infrastructure:** Docker & Docker Compose
- **Integrations:** Brevo (Email/Anymail), Google Calendar (OAuth2), Google GenAI (Anomaly Detection)

---

## 🏗️ Architecture & Project Structure

The project follows a modular Django app-based architecture:

- `core/`: Custom User model, `TenantModel` (abstract base for multi-tenancy), profile settings, and shared utilities.
- `invoices/`: Core invoicing logic, payment tracking, credit notes, and reconciliation.
- `items/`: Management of billable items (recurring and ad-hoc).
- `billing_schedule/`: Logic for billing policies (e.g., "1st of month", "First working day").
- `timesheets/`: Billable hour tracking and automated collation into invoices.
- `clients/`: Client management and payment terms.
- `events/`: Calendar integration and scheduling.
- `notifications/`: Real-time system alerts via WebSockets.
- `core_project/`: Project configuration (settings, URLs, ASGI/WSGI).

### Multi-Tenancy
Multi-tenancy is implemented using an isolation-per-user model via `TenantModel`. Almost all business models inherit from `TenantModel`, which includes a `user` field and a custom `TenantManager` to automatically filter queries by the authenticated user.

---

## 🛠️ Development Workflow

### Key Commands

| Task | Command |
|------|---------|
| **Start Web Server** | `python manage.py runserver` |
| **Start Celery Worker** | `celery -A core_project worker --loglevel=info` |
| **Start Celery Beat** | `celery -A core_project beat --loglevel=info` |
| **Run Tests** | `python manage.py test` |
| **Migrations** | `python manage.py makemigrations` / `python manage.py migrate` |
| **Docker Up** | `docker-compose up -d` |
| **Docker Logs** | `docker-compose logs -f` |

### Core Workflows

#### 1. Automated Recurring Billing
- **Task:** `billing_schedule.tasks.process_daily_billing_queue` (runs daily at 00:01).
- **Service:** `items.services.import_recurring_to_invoices`.
- **Process:** Checks for active `BillingPolicy` due today, finds linked `Item`s that haven't been billed this month, creates draft invoices, runs anomaly detection (GenAI), and dispatches emails via Brevo.

#### 2. Timesheet to Invoice Collation
- **Process:** Users log time in `timesheets/`.
- **Trigger:** Manual or automated collation groups all unbilled timesheets and items by client into a single professional invoice.

#### 3. Invoicing & Payments
- **States:** `DRAFT` → `PENDING` (Sent) → `PAID` / `OVERDUE` / `CANCELLED`.
- **Validation:** Strict rules prevent payments on draft/cancelled invoices and ensure totals match.
- **Credit Notes:** Automatically created when a `PAID` invoice is `CANCELLED`.

---

## 📏 Conventions & Standards

### Coding Style
- **Type Hints:** Use Python type hints where possible.
- **Managers:** Business logic for query filtering and total calculations should reside in custom Model Managers (`managers.py`).
- **Services:** Complex cross-app logic (like automated billing) should reside in `services.py` modules.
- **Audit Logging:** Every invoice generation triggers a `BillingAuditLog` and `AuditHistory` entry for compliance and AI training.

### Multi-tenancy Compliance
When writing queries, **ALWAYS** ensure they are filtered by the current user. Using models that inherit from `TenantModel` and their default manager handles this, but be cautious with direct database access or custom queries.

```python
# GOOD: Automatically filtered by user via TenantManager
invoices = Invoice.objects.all()

# CAUTION: Ensure user context is preserved
from django.db import connection
# Avoid raw queries unless absolutely necessary and scoped to the user
```

### Testing Practices
- Tests are located in `tests.py` or `tests/` directories within each app.
- Focus on verifying the billing logic and data integrity.
- Use `items.tests.test_recurring_invoicing` as a reference for complex integration tests.

---

## 📅 Automated Tasks (Celery Beat)

- `daily-billing-policy-queue`: Runs at 00:01 daily.
- `sync-all-users-events-with-calendar`: Runs every 5 minutes.
- `check-completed-calendar-events`: Runs every 15 minutes.

---

## 🔗 External Documentation
- `README.md`: General setup and feature overview.
- `DOCKER_DEPLOYMENT.md`: Production deployment guide.
- `RECONCILIATION_GUIDE.md`: Data integrity verification workflows.
- `MANAGER_METHODS_DOCUMENTATION.md`: Reference for core API and manager methods.
