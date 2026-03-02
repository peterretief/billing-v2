# Billing V2 - Docker Deployment Guide

## Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- At least 4GB RAM available

### Setup Instructions

1. **Clone/Extract the repository**
   ```bash
   cd /opt/billing_v2
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env with your specific configuration
   nano .env
   ```

3. **Build and start all services**
   ```bash
   docker-compose up -d
   ```

4. **Run migrations**
   ```bash
   docker-compose exec web python manage.py migrate
   ```

5. **Create superuser (admin account)**
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

6. **Access the application**
   - Web App: http://localhost:8000
   - Admin Panel: http://localhost:8000/admin/
   - Celery Monitoring (Flower): http://localhost:5555

## Services

### 1. **PostgreSQL Database** (db)
- Image: `postgres:16-alpine`
- Port: 5432
- Volume: `postgres_data` (persistent)
- Credentials: See `.env` file

### 2. **Redis Cache & Broker** (redis)
- Image: `redis:7-alpine`
- Port: 6379
- Volume: `redis_data` (persistent)
- Used by: Celery, caching

### 3. **Django Web Application** (web)
- Custom image built from Dockerfile
- Port: 8000
- Features:
  - Gunicorn WSGI server (4 workers)
  - Automatic migrations on startup
  - Static file collection
  - Volume: `./` (mounted for hot-reload in development)

### 4. **Celery Worker** (celery_worker)
- Processes async tasks (emails, reports, etc.)
- Concurrency: 4 processes
- Auto-restarts on failure

### 5. **Celery Beat** (celery_beat)
- Scheduler for periodic tasks
- Runs billing policies at scheduled times
- Database scheduler (stores schedules in DB)

### 6. **Celery Flower** (flower)
- Monitoring dashboard for Celery tasks
- Port: 5555
- Access at http://localhost:5555

## Common Commands

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f celery_worker
docker-compose logs -f celery_beat
```

### Run Django commands
```bash
# Migrations
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate

# Tests
docker-compose exec web python manage.py test

# Shell
docker-compose exec web python manage.py shell

# Create admin user
docker-compose exec web python manage.py createsuperuser
```

### Stop all services
```bash
docker-compose down

# Also remove volumes (WARNING: deletes all data)
docker-compose down -v
```

### Restart services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart web
docker-compose restart celery_worker
```

## Environment Variables

Key variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | Required | Change this in production! |
| `DEBUG` | `False` | Set to `True` only in development |
| `DB_PASSWORD` | `billing_password` | PostgreSQL password |
| `REDIS_PASSWORD` | `220961` | Redis password |
| `BREVO_API_KEY` | Optional | Email service API key |
| `GOOGLE_GENAI_API_KEY` | Optional | AI service API key |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |

## Production Deployment

### Important Security Steps

1. **Change SECRET_KEY**
   ```bash
   # Generate new secret key
   python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
   # Update in .env
   ```

2. **Set DEBUG=False**
   ```
   DEBUG=False
   ```

3. **Update ALLOWED_HOSTS**
   ```
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   ```

4. **Use strong passwords**
   - Update DB_PASSWORD
   - Update REDIS_PASSWORD

5. **Use environment-specific .env**
   - Keep `.env` file out of version control
   - Use Docker secrets or external vault in production

6. **Set up reverse proxy (Nginx/Traefik)**
   - Handle SSL/TLS termination
   - Load balancing
   - Example: See `nginx.conf.example` (create if needed)

## Scaling

### Increase Celery Worker Concurrency
Edit `docker-compose.yml`, change worker command:
```yaml
command: celery -A core_project worker --loglevel=info --concurrency=8
```

### Add More Gunicorn Workers
Edit `docker-compose.yml`, change web command:
```yaml
command: gunicorn --bind 0.0.0.0:8000 --workers 8 --timeout 120 core_project.wsgi:application
```

### Multiple Celery Workers
```bash
docker-compose up -d --scale celery_worker=3
```

## Backup & Restore

### Backup PostgreSQL
```bash
docker-compose exec db pg_dump -U billing_user billing_v2_db > backup.sql
```

### Restore PostgreSQL
```bash
cat backup.sql | docker-compose exec -T db psql -U billing_user billing_v2_db
```

### Backup Redis
```bash
docker-compose exec redis redis-cli BGSAVE
docker cp billing_redis:/data/dump.rdb ./redis_backup.rdb
```

## Troubleshooting

### Web app won't start
```bash
docker-compose logs web
# Check for migration errors
docker-compose exec web python manage.py migrate --noinput
```

### Celery tasks not running
```bash
docker-compose logs celery_worker
docker-compose logs celery_beat
# Check if Redis is running
docker-compose exec redis redis-cli ping
```

### Database connection errors
```bash
# Check PostgreSQL is running
docker-compose exec db pg_isready
# Check environment variables
docker-compose config | grep DB_
```

### Static files not loading
```bash
docker-compose exec web python manage.py collectstatic --noinput --clear
```

## Development vs Production

### Development (current setup)
- `DEBUG=True`
- Hot-reload enabled
- Local volumes mounted
- Single worker processes

### Production Changes Needed
1. Set `DEBUG=False`
2. Use external database (not container-based)
3. Use external Redis cluster
4. Add SSL/TLS with reverse proxy
5. Increase workers/concurrency
6. Use environment management (Secrets, Vault)
7. Add monitoring & logging (Prometheus, ELK, Sentry)
8. Implement backup strategy

## Monitoring

### Flower Dashboard
Access http://localhost:5555 to monitor:
- Active tasks
- Completed tasks
- Failed tasks
- Worker status
- Task history

### Database Health
```bash
docker-compose exec db pg_isready
```

### Redis Health
```bash
docker-compose exec redis redis-cli ping
```

## Support & Documentation

For more information about the billing system, see:
- `IMPLEMENTATION_SUMMARY_CLIENT_SUMMARY.md` - Feature overview
- `RECONCILIATION_GUIDE.md` - Data integrity
- `INVOICE_CANCELLATION_RULES.md` - Business rules

---

**Happy Billing! 🚀**
