import os
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

# Celery Beat schedule - runs daily billing task at 00:01 Africa/Johannesburg time

from celery.schedules import crontab


CELERY_BEAT_SCHEDULE = {
    "daily-billing-policy-queue": {
        "task": "billing_schedule.tasks.process_daily_billing_queue",
        "schedule": crontab(minute=1, hour=0),  # Run at 00:01 daily
    },

    "sync-all-users-events-with-calendar": {
        "task": "events.tasks.sync_all_users_events_with_calendar",
        "schedule": crontab(minute="*/5"),  # Run every 5 minutes
    },
    "cleanup-old-sync-logs": {
        "task": "events.tasks.cleanup_old_sync_logs",
        "schedule": crontab(minute=0, hour=2),  # Run at 02:00 daily
    },
}


TIME_ZONE = "Africa/Johannesburg"
USE_TZ = True
CELERY_TIMEZONE = "Africa/Johannesburg"

# --- PATHS & ENVIRONMENT ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- CORE SETTINGS ---
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-b9=kayw#kvdwn!5mo=7#tsyxph)6j2&gu$nswyx(20deuyt5wl")
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")


ALLOWED_HOSTS = [
    "peterretief.org",
    "www.peterretief.org",
    "192.168.0.101",
    "127.0.0.1",
    "localhost",
    "peter-All-Series",
]

# --- SECURITY & CLOUDFLARE HANDSHAKE ---
# This is the most critical section for your Port 81 + Cloudflare setup
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookie Security (Must be True for HTTPS)
CSRF_COOKIE_NAME = "billing_v2_csrftoken"
SESSION_COOKIE_NAME = "billing_v2_sessionid"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    "https://peterretief.org",
    "https://peterretief.org:81",
]

# Disable strict referer check for complex proxy setups (Solves the "4th attempt" glitch)
CSRF_CHECK_REFERER = False

# --- APPLICATION DEFINITION ---
INSTALLED_APPS = [
    # "ops",  # Disabled for now, can be re-enabled later if needed
    "daphne",  # ASGI server for Channels - must be first
    "channels",  # WebSocket support
    "billing_schedule",
    "core",
    "anymail",
    "clients",
    "invoices",
    "timesheets",
    "events",
    # "todos",  # Deprecated - renamed to events app
    "items",
    "notifications",
    "widget_tweaks",
    "crispy_forms",
    "crispy_bootstrap5",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "debug_toolbar",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",  # 1. Load the session first
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # 2. Check CSRF after session is loaded
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # 3. Then authenticate the user
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "core.middleware.UserTimezoneMiddleware",  # Add at the bottom
]


ROOT_URLCONF = "core_project.urls"
WSGI_APPLICATION = "core_project.wsgi.application"
ASGI_APPLICATION = "core_project.asgi.application"
AUTH_USER_MODEL = "core.User"

# --- TEMPLATES ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "timesheets.context_processors.unbilled_count",
                "notifications.context_processors.onboarding",
                "core.context_processors.vat_settings",
                "core.context_processors.currency_settings",
            ],
        },
    },
]

# --- DATABASE ---
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "billing_v2_db"),
        "USER": os.environ.get("DB_USER", "billing_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),  # Empty in Docker (uses .env), set manually for local dev
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}


# --- STATIC & MEDIA ---
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

# --- EMAIL (BREVO/ANYMAIL) ---
EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
ANYMAIL = {"BREVO_API_KEY": os.environ.get("BREVO_API_KEY")}
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "peter@diode.co.za")
SERVER_EMAIL = "info@peterretief.org"
BREVO_WEBHOOK_SECRET = os.environ.get("BREVO_WEBHOOK_SECRET")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")


# --- REDIS & CELERY ---
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "0")
CELERY_BROKER_URL = (
    f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    if REDIS_PASSWORD
    else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)
CELERY_RESULT_BACKEND = (
    f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    if REDIS_PASSWORD
    else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)
CELERY_TASK_ALWAYS_EAGER = False  # Set to False to actually use Redis
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# --- CHANNELS (WebSocket) ---
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (
                    REDIS_HOST,
                    int(REDIS_PORT),
                )
                if not REDIS_PASSWORD
                else f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"
            ],
        },
    },
}

# --- MISC ---
LOGIN_REDIRECT_URL = "/invoices/"
LOGOUT_REDIRECT_URL = "/"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
USE_THOUSAND_SEPARATOR = True
INTERNAL_IPS = ["127.0.0.1"]

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: False,  # Change to True to debug locally
}

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.path.join(BASE_DIR, "tmp", "email_status.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

# --- GOOGLE CALENDAR OAUTH ---
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_CREDENTIALS_PATH = os.path.join(BASE_DIR, "google_credentials.json")
GOOGLE_OAUTH_REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8003/calendar/auth/callback/")
