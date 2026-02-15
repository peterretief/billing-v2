import os
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

CELERY_BEAT_SCHEDULE = {
    'daily-billing-automation': {
        'task': 'tasks.run_automated_billing_cycle',
        'schedule': crontab(hour=0, minute=1), # Runs at 12:01 AM every day
    },
}


TIME_ZONE = 'Africa/Johannesburg'
USE_TZ = True
CELERY_TIMEZONE = 'Africa/Johannesburg'

# --- PATHS & ENVIRONMENT ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# --- CORE SETTINGS ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-b9=kayw#kvdwn!5mo=7#tsyxph)6j2&gu$nswyx(20deuyt5wl')
DEBUG = True

ALLOWED_HOSTS = [
    'peterretief.org',
    'www.peterretief.org',
    '192.168.0.101',
    '127.0.0.1',
    'localhost',
    'peter-All-Series',
]

# --- SECURITY & CLOUDFLARE HANDSHAKE ---
# This is the most critical section for your Port 81 + Cloudflare setup
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Cookie Security (Must be True for HTTPS)
CSRF_COOKIE_NAME = 'billing_v2_csrftoken'
SESSION_COOKIE_NAME = 'billing_v2_sessionid'
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    'https://peterretief.org',
    'https://peterretief.org:81',
]

# Disable strict referer check for complex proxy setups (Solves the "4th attempt" glitch)
CSRF_CHECK_REFERER = False

# --- APPLICATION DEFINITION ---
INSTALLED_APPS = [
    'ops',
    'billing_schedule',
    'core',
    'anymail',
    'clients',
    'invoices',
    'timesheets',
    'items',
    'notifications',
    'widget_tweaks',
    'crispy_forms',
    'crispy_bootstrap5',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'debug_toolbar',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # 1. Load the session first
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',             # 2. Check CSRF after session is loaded
    'django.contrib.auth.middleware.AuthenticationMiddleware', # 3. Then authenticate the user
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]


ROOT_URLCONF = 'core_project.urls'
WSGI_APPLICATION = 'core_project.wsgi.application'
AUTH_USER_MODEL = 'core.User'

# --- TEMPLATES ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'timesheets.context_processors.unbilled_count',
                'notifications.context_processors.onboarding',
                'core.context_processors.currency_settings',
            ],
        },
    },
]

# --- DATABASE ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'billing_v2_db',
        'USER': 'peter',
        'PASSWORD': '220961',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}


# --- STATIC & MEDIA ---
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# --- EMAIL (BREVO/ANYMAIL) ---
EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
ANYMAIL = {"BREVO_API_KEY": os.environ.get("BREVO_API_KEY")}
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'peter@diode.co.za')
SERVER_EMAIL = "info@peterretief.org"

# --- REDIS & CELERY ---
REDIS_PASSWORD = {"REDIS_PASSWORD": os.environ.get("REDIS_PASSWORD")}
CELERY_BROKER_URL = 'redis://:220961@localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://:220961@localhost:6379/0'
CELERY_TASK_ALWAYS_EAGER = False  # Set to False to actually use Redis
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# --- MISC ---
LOGIN_REDIRECT_URL = '/invoices/'
LOGOUT_REDIRECT_URL = '/'
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
USE_THOUSAND_SEPARATOR = True
INTERNAL_IPS = ['127.0.0.1']

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: False, # Change to True to debug locally
}

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')