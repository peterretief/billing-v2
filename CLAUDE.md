# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

**Billing V2** is a multi-tenant Django billing platform for freelancers/agencies. Core workflows:
- **Recurring invoicing**: Service items → billing policies → automated monthly invoice generation via Celery
- **Timesheet billing**: Log hours throughout month → collate by client → generate invoices with PDF timesheet attachments
- **Invoice lifecycle**: DRAFT → PENDING → SENT → PAID/OVERDUE, with payments, credit notes, and email tracking via Brevo

## Commands

### Local Development
```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in values
python manage.py migrate
python manage.py runserver           # Terminal 1
celery -A core_project worker --loglevel=info  # Terminal 2
celery -A core_project beat --loglevel=info    # Terminal 3
```

### Docker (Recommended)
```bash
./docker-setup.sh
# Services: web:8000, postgres:5432, redis:6379, flower:5555
```

### Tests
```bash
python manage.py test                                          # all tests
python manage.py test invoices.tests.test_new_data_integrity -v 2  # specific module
python manage.py test items.tests.test_recurring_invoicing    # specific module
```

### Linting
```bash
ruff check .
ruff check --fix .
```

Ruff is configured in `pyproject.toml`: line length 120, rules E/F/I, F401 ignored in `apps.py`, `signals.py`, `__init__.py`.

## Architecture

### Multi-Tenancy
Every model inherits from `core.models.TenantModel`, which automatically adds `user`, `created_at`, `updated_at`. The `TenantManager` always filters by `request.user` — data isolation is automatic. Never bypass the manager with raw querysets unless you understand the tenancy implications.

### Django Apps

| App | Responsibility |
|-----|---------------|
| `core` | Custom `User` model (`AUTH_USER_MODEL`), `TenantModel`/`TenantManager` base classes, `UserProfile` (VAT, currency, branding), auth, middleware |
| `invoices` | Invoice CRUD, status machine, payment recording, credit notes, email status log, PDF generation |
| `clients` | Client records, payment terms, hourly rates, target hours |
| `items` | One-time and recurring `Item` + `ServiceItem` models; `services.py` handles importing recurring items into invoices |
| `billing_schedule` | `BillingPolicy` model ties clients/items to run dates; `tasks.py::process_daily_billing_queue` runs at 00:01 Africa/Johannesburg |
| `timesheets` | `TimesheetEntry` + `WorkCategory`; bulk billing collates unbilled entries per client |
| `integrations` | Third-party service integrations (Brevo email, etc.) |
| `notifications` | Internal system notifications |
| `events` | Google Calendar integration (partial) |
| `inventory` | Inventory tracking (supplemental feature) |
| `recipes` | Recipe/formula management (add-on) |

### Key Data Relationships
```
User → UserProfile
User → Client (1:N)
  Client → Invoice (1:N)
    Invoice → Item (billed items, N:M)
    Invoice → TimesheetEntry (billed time, N:M)
    Invoice → Payment (1:N)
    Invoice → InvoiceEmailStatusLog (1:N)
  Client → Item (unbilled, 1:N)
  Client → TimesheetEntry (unbilled, 1:N)
  Client → BillingPolicy (1:N)
    BillingPolicy → Item / ServiceItem (N:M)
```

### Async / Celery
- Broker + result backend: Redis
- Beat scheduler: `django_celery_beat.schedulers.DatabaseScheduler`
- Key tasks: `billing_schedule.tasks.process_daily_billing_queue` (daily cron), `invoices.tasks.send_invoice_async`, `invoices.tasks.generate_ai_insights_task` (Google GenAI)
- Monitor via Flower at `http://localhost:5555`

### External Services
- **Email**: Brevo (Sendinblue) via `django-anymail` — `anymail.backends.brevo.EmailBackend`
- **AI insights**: Google GenAI (`GOOGLE_GENAI_API_KEY`)
- **Calendar**: Google Calendar OAuth (`google_credentials.json`)

### Settings of Note
- `TIME_ZONE = "Africa/Johannesburg"` — billing logic is timezone-sensitive
- `CELERY_BEAT_SCHEDULE` in `settings.py` defines the daily billing cron
- `BillingPolicy.special_rule`: `"WORK"` = first working day of month, `"NONE"` = exact date
- `Invoice.status` choices: `DRAFT`, `PENDING`, `OVERDUE`, `PAID`, `CANCELLED`, `SENT`

### Tests
Base class for billing tests: `core.tests.test_legacy.BaseBillingTest` — sets up user, authenticated client, and profile. Most test files live under `invoices/tests/` (19+ files) and `timesheets/tests/`.
