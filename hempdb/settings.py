from pathlib import Path
from dotenv import load_dotenv
import os
import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from hempdb.csp import build_csp_directives, validate_report_uri
from hempdb.environment import env_bool, env_rate

load_dotenv()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY environment variable is required.')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DEBUG', False)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', '*').split(',')
    if host.strip()
]
# Canonical public hostname
PRODUCTION_URL = os.getenv('PRODUCTION_URL', 'hempdb.vercel.app')

# For fetching datetime fields
USE_TZ = True       # Make datetime objects timezone-aware
TIME_ZONE = 'America/Los_Angeles'   # PST time, automatically handles daylight savings?

OPTIONS = {
    'init_command': "SET time_zone='+00:00';"
}

INTERNAL_IPS = [
    "127.0.0.1",
]

# Logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'root': {
        'handlers' : ['console'],
        'level' : 'WARNING'
    },
    'loggers': {
        'helloworld': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False
        },
        'django-cron': {
            'handlers': ['mail_admins', 'console'],
            'level': 'ERROR',
            'propagate': True
        }
    },
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'helloworld.apps.HelloworldConfig',
    'crispy_forms',
    'django_bootstrap5',
    'crispy_bootstrap5',
    'django_cron',
    'csp',
]

SECURE_REFERRER_POLICY = 'same-origin'
PERMISSIONS_POLICY = 'camera=(), geolocation=(), microphone=(), payment=(), usb=()'

MIDDLEWARE = [
    'hempdb.middleware.PermissionsPolicyMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'csp.middleware.CSPMiddleware',
    'hempdb.middleware.CSPReportingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

csp_report_uri = validate_report_uri(os.getenv('CSP_REPORT_URI'))
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': build_csp_directives(csp_report_uri),
}

# Top-level URLs
ROOT_URLCONF = 'hempdb.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hempdb.wsgi.app'

# MySQL DB config
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL environment variable is required.')

DATABASE_SSL = env_bool('DATABASE_SSL', True)
DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=DATABASE_SSL,
    )
}
database_options = DATABASES['default'].setdefault('OPTIONS', {})
database_options['charset'] = 'utf8mb4'
database_options.pop('sslmode', None)
if DATABASE_SSL:
    database_options['ssl'] = {'ca': os.getenv('MYSQL_ATTR_SSL_CA')}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles_build' / 'static'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth Redirects and config
LOGIN_URL = "/user/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Crispy Forms (crispy_bootstrap5)
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# Sentry config
SENTRY_DSN = os.getenv('SENTRY_DSN', '').strip()
SENTRY_ENVIRONMENT = (
    os.getenv('SENTRY_ENVIRONMENT', '').strip()
    or ('development' if DEBUG else 'production')
)
SENTRY_RELEASE = os.getenv('SENTRY_RELEASE', '').strip() or None
SENTRY_TRACES_SAMPLE_RATE = env_rate('SENTRY_TRACES_SAMPLE_RATE', 0.1)
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )

# Configuration for sending emails
# https://docs.djangoproject.com/en/5.1/topics/email/
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', not DEBUG)
EMAIL_HOST_USER = os.getenv('EMAIL_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_APP_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    EMAIL_HOST_USER or 'webmaster@localhost',
)
EMAIL_LINK = os.getenv(
    'EMAIL_LINK',
    'http://localhost:8000' if DEBUG else f'https://{PRODUCTION_URL}',
)

REDIS_URL = os.getenv('REDIS_URL', '').strip()
if not REDIS_URL:
    raise RuntimeError('REDIS_URL environment variable is required.')
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CRON_CLASSES = [
    "helloworld.cron.CronAudit",
]

# Fill in for administrators/developers to receive emails about cron jobs with (Name, Email)
ADMINS = []
