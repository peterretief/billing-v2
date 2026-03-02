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

## 🔄 Billing Workflow

### 1. Create Billing Policy
- Navigate to `/scheduler/policies/`
- Define:
  - **Name:** e.g., "Monthly Service"
  - **Run Day:** Day of month (1-31) or "First Working Day"
  - **Status:** Active/Inactive

### 2. Link Items to Policy
- Create recurring items in `/items/`
- Select billing policy
- Mark as recurring
- Set initial `last_billed_date`

### 3. Automatic Processing
- **Daily at 00:01 (UTC+2):** Celery Beat triggers scheduler
- **Process:** `billing_schedule.tasks.process_daily_billing_queue`
- **Checks:** Which policies are due today
- **Action:** Creates invoices for matching items
- **Safety:** Prevents duplicates within same month

### 4. Email Delivery
- Invoices emailed via Brevo API
- Status marked as "PENDING"
- `emailed_at` timestamp recorded

### 5. Payment Tracking
- Record payments manually or via webhook
- System updates invoice status to "PAID"
- Reconciliation verifies amounts

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
