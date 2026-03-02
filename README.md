# Billing V2 - Advanced Django Billing System

A comprehensive, production-ready billing platform built with Django, Celery, and PostgreSQL. Handles recurring invoices, client management, reconciliation, and automated scheduling.

## 🌟 Features

### Core Billing
- ✅ **Recurring Invoicing** — Automatic monthly billing based on custom policies
- ✅ **Invoice Management** — Create, edit, send, and track invoices
- ✅ **Client Management** — Multi-tenant support with client profiles
- ✅ **Payment Tracking** — Record and reconcile payments
- ✅ **Quote Workflow** — Create quotes and convert to invoices
- ✅ **Credit Notes** — Handle refunds and adjustments

### Advanced Features
- 🤖 **AI Insights** — Anomaly detection using Google GenAI
- 📧 **Email Integration** — Automated invoice delivery via Brevo
- ⏱️ **Timesheet Management** — Log hours, track by category, generate invoices
- 📊 **Reconciliation** — Data integrity checks and dual verification
- 📈 **Analytics Dashboard** — Real-time financial metrics
- 🔔 **Notifications** — Client alerts and system notifications
- ⏰ **Flexible Scheduling** — First working day, specific dates, or custom rules

### Technical
- 🐳 **Docker & Docker Compose** — Full containerization
- 🔄 **Celery + Redis** — Async task processing & scheduling
- 📊 **PostgreSQL** — Robust relational database
- 🔐 **Multi-tenancy** — Isolated user data
- 🧪 **Comprehensive Tests** — 10+ tests for recurring invoicing
- 🛡️ **Security** — CSRF protection, SSL/TLS ready, audit logging

## 📋 Prerequisites

### Option 1: Docker (Recommended)
- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum

### Option 2: Local Development
- Python 3.12+
- PostgreSQL 14+
- Redis 7+
- pip or poetry

## 🚀 Quick Start with Docker

### 1. Clone Repository
```bash
git clone <repository-url>
cd billing_v2
```

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env with your configuration
nano .env
```

**Key variables to update:**
```env
DJANGO_SECRET_KEY=your-secret-key-here
DB_PASSWORD=strong-password
REDIS_PASSWORD=strong-password
BREVO_API_KEY=your-email-api-key
GOOGLE_GENAI_API_KEY=your-ai-api-key
```

### 3. Run Setup Script
```bash
chmod +x docker-setup.sh
./docker-setup.sh
```

Or manually:
```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### 4. Access Application
- **Web App:** http://localhost:8000
- **Admin Panel:** http://localhost:8000/admin
- **Monitoring:** http://localhost:5555 (Celery Flower)

## 🛠️ Local Development Setup

### Prerequisites
```bash
# Install Python 3.12
python3.12 --version

# Install PostgreSQL
brew install postgresql  # macOS
# or
sudo apt-get install postgresql  # Ubuntu

# Install Redis
brew install redis  # macOS
# or
sudo apt-get install redis-server  # Ubuntu
```

### Setup
```bash
# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env
cp .env.example .env

# Configure database in .env
# DATABASES should use your local PostgreSQL
```

### Run Services
```bash
# Terminal 1: Django development server
python manage.py runserver

# Terminal 2: Celery worker
celery -A core_project worker --loglevel=info

# Terminal 3: Celery Beat (scheduler)
celery -A core_project beat --loglevel=info

# Terminal 4: Redis (if not already running)
redis-server
```

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | Complete Docker guide, scaling, troubleshooting |
| [RECONCILIATION_GUIDE.md](RECONCILIATION_GUIDE.md) | Data integrity & verification workflows |
| [INVOICE_CANCELLATION_RULES.md](INVOICE_CANCELLATION_RULES.md) | Cancellation policies & rules |
| [MANAGER_METHODS_DOCUMENTATION.md](MANAGER_METHODS_DOCUMENTATION.md) | API & manager methods reference |

## 🗂️ Project Structure

```
billing_v2/
├── billing_schedule/        # Recurring billing policies
├── clients/                 # Client management
├── core/                    # Core models & authentication
├── invoices/                # Invoice & payment handling
├── items/                   # Line items & recurring templates
├── timesheets/              # Timesheet integration
├── notifications/           # Alert system
├── templates/               # HTML templates
├── static/                  # CSS, JS, images
├── core_project/            # Django settings & config
│   ├── settings.py          # Main configuration
│   ├── celery.py            # Celery setup
│   └── urls.py              # URL routing
├── docker-compose.yml       # Service orchestration
├── Dockerfile               # Container image build
├── requirements.txt         # Python dependencies
└── manage.py                # Django management
```
## 📊 Billing Approaches

This system supports **two primary billing workflows** to fit your business needs:

### Option 1: Recurring Invoicing (Set & Forget)
**Perfect for:** Fixed monthly services, subscriptions, retainers

**How it works:**
1. Create recurring items once (e.g., "Monthly hosting", "Support retainer")
2. Set a billing policy (e.g., "Bill on the 1st of each month")
3. The system **automatically invoices your clients every month** — no further action needed
4. Invoices are generated at the scheduled time and emailed to clients

**Example:**
```
March 1: Customer A invoiced $1,000 for hosting
April 1: Customer A automatically invoiced again $1,000
May 1: Customer A automatically invoiced again $1,000
... continues every month
```

### Option 2: Accumulate & Invoice (Timesheets + Ad-Hoc Items)
**Perfect for:** Project work, hourly billing, variable services

**How it works:**
1. **All month long:** Log timesheet entries OR add ad-hoc items as work is completed
   - Log time spent on projects (e.g., 8 hours Dev work = $2,000)
   - Add miscellaneous items (e.g., "Server upgrade" = $500)
   - Items and timesheets for each client accumulate in the system
2. **End of month:** Trigger bulk invoicing (automatically or manually)
   - All accumulated timesheets and items are collated into correct invoices per client
   - One invoice per client containing all their work for the month
   - Invoices are emailed to clients automatically

**Example:**
```
March 5:  Log 4 hours Dev work for Client A = $1,000
March 10: Log 2 hours QA work for Client A = $500
March 12: Add miscellaneous item to Client B = $800
March 15: Log meeting time for Client A = $300
March 20: Log 6 hours Dev work for Client B = $1,500

March 31 at 00:01 (or manual trigger):
  → Client A invoice created: Dev (4h) + QA (2h) + Meeting (1h) = $1,800
  → Client B invoice created: Dev (6h) + Misc item = $2,300
  → Invoices emailed to both clients
```

---
## 🔄 Billing Workflow

### Recurring Invoices (Automatic)

#### 1. Create Billing Policy
- Navigate to `/scheduler/policies/`
- Define:
  - **Name:** e.g., "Monthly Service"
  - **Run Day:** Day of month (1-31) or "First Working Day"
  - **Status:** Active/Inactive

#### 2. Link Items to Policy
- Create recurring items in `/items/` (e.g., "Hosting", "Support retainer")
- Select billing policy
- Mark as recurring
- Set initial `last_billed_date`

#### 3. Automatic Daily Processing
- **When:** Daily at 00:01 (UTC+2) via Celery Beat
- **Process:** `billing_schedule.tasks.process_daily_billing_queue`
- **Check:** Which policies are due today
- **Action:** Creates invoices for all matching recurring items
- **Safety:** Prevents duplicates within same month

#### 4. Email Delivery
- Invoices automatically emailed via Brevo API
- Status marked as "PENDING"
- `emailed_at` timestamp recorded

#### 5. Payment Tracking
- Record payments manually or via webhook
- System updates invoice status to "PAID"
- Reconciliation verifies amounts

---

### Accumulate & Invoice (Timesheets + Items)

#### 1. Throughout the Month
- **Log Timesheets:** Visit `/timesheets/log-time/` and record work (hours, rate, category)
- **Add Items:** Create ad-hoc items in `/items/` for one-time charges
- **Accumulate:** All entries accumulate in the system — nothing is invoiced yet

#### 2. Smart Collation
When invoicing is triggered, the system automatically:
- Groups all timesheets and items by client
- Consolidates multiple entries into single invoices per client
- Prevents double-invoicing of the same work

#### 3. Generate Invoices
- **Option A (Automatic):** At scheduled policy date, system generates invoices from all accumulated timesheets + items
- **Option B (Manual):** Visit `/invoices/` and click "Generate from Timesheets" for specific entries
- Result: One professional invoice per client with all their work itemized

#### 4. Email & Payment Tracking
- Invoices emailed to clients via Brevo
- Status marked as "PENDING"
- Record payments as they arrive
- System marks invoice as "PAID"

## ⏱️ Timesheet Management

Track billable hours all month, then automatically generate properly collated invoices for all clients.

### Features
- **Time Entry Logging** — Log hours with date, category, and hourly rate as work is completed
- **Custom Categories** — Create work categories (Development, Meetings, Support, etc.)
- **Metadata Tracking** — Add custom fields to entries (Attendees, Location, etc.)
- **Unbilled Hours Report** — View all time entries waiting to be invoiced (sorted by client)
- **Smart Bulk Invoicing** — Convert multiple timesheet entries into correctly collated invoices per client
- **Automatic Grouping** — System intelligently groups and consolidates items for each client into single invoices
- **Time Report PDF** — Generate detailed timesheet reports with metadata
- **Audit Trail** — Track which timesheets are billed and linked to invoices

### Workflow

#### 1. Create Work Categories
- Navigate to `/timesheets/manage-categories/`
- Define categories: Development, Meetings, Support, etc.
- Optionally add metadata fields (Attendees, Location, etc.)

#### 2. Log Time Throughout the Month
- Visit `/timesheets/log-time/` and start logging as you work
- Select client and category
- Enter date, hours, and hourly rate
- Add optional metadata (attendees, notes, etc.)
- Submit — entries accumulate in the system, nothing invoiced yet
- **Repeat all month** — log different clients, projects, work types

#### 3. View Accumulated Unbilled Hours
- Navigate to `/timesheets/` — see all logged time organized by client
- Filter by client or date range to review before invoicing
- See total monetary value of unbilled hours per client
- Preview exactly what each client will be invoiced for

#### 4. Generate Invoice from Timesheets (Smart Collation)
- Click "Generate Invoice" for unbilled entries
- System automatically groups timesheets and items by client
- **Smart collation:** Multiple entries from the same client → single professional invoice
  - Client A: Dev time + Meetings + Misc items = ONE invoice
  - Client B: Support time + Dev time = ONE invoice
- Each work entry becomes a line item (description, hours, rate, subtotal)
- Invoice ready to send to client

#### 5. Generate Time Report PDF
- From generated invoice: `/invoices/<id>/time-report/`
- PDF includes:
  - All timesheet entries with descriptions
  - Formatted metadata (Attendees, Location, etc.)
  - Hours worked, hourly rates, and totals
  - Professional formatting for client delivery
  - Can be emailed with invoice

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/timesheets/` | GET | List all timesheet entries (current user) |
| `/timesheets/log-time/` | POST | Create new timesheet entry |
| `/timesheets/<id>/edit/` | POST | Update existing entry |
| `/timesheets/<id>/delete/` | POST | Delete entry |
| `/timesheets/manage-categories/` | GET/POST | Manage work categories |
| `/invoices/<id>/time-report/` | GET | Generate PDF report |
| `/timesheets/invoice-bulk/` | POST | Convert timesheets to invoice |

### Database Models

**TimesheetEntry**
- `user` — Owner
- `client` — Client to bill
- `category` — Work type
- `date` — Date of work
- `hours` — Hours worked (decimal)
- `hourly_rate` — Rate per hour
- `is_billed` — Whether converted to invoice
- `invoice` — Link to generated invoice
- `metadata` — Custom fields (JSON)

**WorkCategory**
- `user` — Owner
- `name` — Category name
- `metadata_schema` — List of custom field names

### Example: Track Development Work
```
Date: 2026-03-02
Client: Acme Corp
Category: Development
Hours: 4.5
Hourly Rate: $75
Metadata: {
  "Task": "Build API endpoint",
  "Ticket": "#1234"
}
```

Then later:
```bash
# Select this entry + others for same client
# Click "Generate Invoice"
# Creates invoice line: "2026-03-02: Development - Build API endpoint (4.5 hrs × $75)"
```

### Example Reports
- **Client Unbilled Hours:** How many hours waiting to be billed?
- **Timesheet Report:** PDF with all hours, rates, and metadata for client
- **Category Usage:** How many hours in each category this month?

## 🧪 Testing

### Run All Tests
```bash
# With Docker
docker-compose exec web python manage.py test

# Locally
python manage.py test
```

### Run Specific Tests
```bash
# Recurring invoicing tests
python manage.py test items.tests.test_recurring_invoicing -v 2

# Invoice data integrity
python manage.py test invoices.tests.test_new_data_integrity -v 2
```

### Test Coverage
- 10+ tests for recurring billing
- Invoice creation, emailing, deduplication
- Monthly rollover safety
- Policy scheduling logic

## 🔑 Key API Endpoints

### Invoices
- `GET /invoices/` — List invoices
- `POST /invoices/create/` — Create invoice
- `GET /invoices/<id>/` — Invoice detail
- `POST /invoices/<id>/send/` — Send invoice

### Clients
- `GET /clients/` — List clients
- `POST /clients/create/` — Create client
- `GET /clients/<id>/` — Client detail

### Items
- `GET /items/` — List items
- `POST /items/create/` — Create item
- `GET /items/<id>/` — Item detail

### Scheduler
- `GET /scheduler/policies/` — List billing policies
- `POST /scheduler/policies/create/` — Create policy

### Timesheets
- `GET /timesheets/` — List timesheet entries
- `POST /timesheets/log-time/` — Create new entry
- `POST /timesheets/<id>/edit/` — Update entry
- `POST /timesheets/<id>/delete/` — Delete entry
- `GET /timesheets/manage-categories/` — Manage work categories
- `GET /invoices/<id>/time-report/` — Generate timesheet report PDF
- `POST /timesheets/invoice-bulk/` — Convert timesheets to invoice

See [MANAGER_METHODS_DOCUMENTATION.md](MANAGER_METHODS_DOCUMENTATION.md) for complete API reference.

## ⚙️ Configuration

### Environment Variables
See [.env.example](.env.example) for all available options.

**Critical for production:**
```env
DEBUG=False
SECRET_KEY=generate-new-secure-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_PASSWORD=strong-password
REDIS_PASSWORD=strong-password
BREVO_API_KEY=your-email-api-key
GOOGLE_GENAI_API_KEY=your-ai-api-key
```

### Database
- **Default:** PostgreSQL (recommended)
- **Fallback:** SQLite (development only)
- Run migrations: `python manage.py migrate`

### Celery
- **Broker:** Redis
- **Result Backend:** Redis
- **Beat Scheduler:** Celery Beat (with database store)
- **Monitoring:** Flower (http://localhost:5555)

## 🐳 Docker Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Django Web | billing_web | 8000 | Main application |
| PostgreSQL | billing_db | 5432 | Database |
| Redis | billing_redis | 6379 | Cache/broker |
| Celery Worker | billing_celery_worker | - | Task processing |
| Celery Beat | billing_celery_beat | - | Scheduling |
| Flower | billing_flower | 5555 | Monitoring |

### Common Docker Commands
```bash
# View all logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop and remove containers
docker-compose down

# Remove containers AND volumes (WARNING: deletes data)
docker-compose down -v

# Run Django command
docker-compose exec web python manage.py shell

# View database
docker-compose exec db psql -U billing_user -d billing_v2_db
```

## 🔐 Security

### Production Checklist
- [ ] Generate new `SECRET_KEY`
- [ ] Set `DEBUG=False`
- [ ] Update `ALLOWED_HOSTS`
- [ ] Use strong `DB_PASSWORD` and `REDIS_PASSWORD`
- [ ] Set up SSL/TLS with reverse proxy (Nginx)
- [ ] Restrict admin panel access
- [ ] Enable audit logging
- [ ] Set up monitoring & backups

### SSL/TLS Setup
See [nginx.conf.example](nginx.conf.example) for reverse proxy configuration with Let's Encrypt.

## 📊 Monitoring

### Celery Tasks
Access **Flower Dashboard** at http://localhost:5555
- Monitor active/completed tasks
- Check worker status
- View task history

### Database
```bash
# Connect to PostgreSQL
docker-compose exec db psql -U billing_user -d billing_v2_db

# Check invoice count
SELECT COUNT(*) FROM invoices_invoice WHERE status='SENT';

# View recent transactions
SELECT * FROM invoices_invoice ORDER BY date_issued DESC LIMIT 10;
```

### Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f celery_worker
docker-compose logs -f celery_beat
```

## 🆘 Troubleshooting

### Migrations fail
```bash
docker-compose exec web python manage.py migrate --noinput
docker-compose restart web
```

### Celery tasks not running
```bash
# Check if Redis is running
docker-compose exec redis redis-cli ping

# Check Celery worker logs
docker-compose logs celery_worker

# Check Celery Beat logs
docker-compose logs celery_beat
```

### Static files not loading
```bash
docker-compose exec web python manage.py collectstatic --noinput --clear
docker-compose restart web
```

### Database connection error
```bash
# Check PostgreSQL is running
docker-compose exec db pg_isready

# Verify credentials in .env
docker-compose config | grep DB_
```

See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for more troubleshooting.

## 📈 Performance Optimization

### Scaling Celery Workers
```bash
docker-compose up -d --scale celery_worker=3
```

### Increasing Gunicorn Workers
Edit `docker-compose.yml`:
```yaml
command: gunicorn --bind 0.0.0.0:8000 --workers 8 core_project.wsgi:application
```

### Database Connection Pooling
Configure in settings for production:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': 600,  # Connection pooling
        ...
    }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`python manage.py test`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License.

## 📞 Support

For issues, questions, or suggestions:
1. Check existing documentation in the repo
2. Review [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for deployment issues
3. Check [RECONCILIATION_GUIDE.md](RECONCILIATION_GUIDE.md) for data integrity questions
4. Open an issue on GitHub

## 🚀 Deployment

### Production Checklist
- [ ] Update SECRET_KEY
- [ ] Set DEBUG=False
- [ ] Use PostgreSQL (not SQLite)
- [ ] Use external Redis (not container-based)
- [ ] Setup SSL/TLS with Nginx reverse proxy
- [ ] Configure email service (Brevo API key)
- [ ] Setup backup strategy
- [ ] Configure monitoring (Flower, Sentry)
- [ ] Load test with production data
- [ ] Document runbooks

See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for detailed production deployment steps.

---

**Built with ❤️ using Django, Celery, and PostgreSQL**

Last Updated: March 2, 2026
