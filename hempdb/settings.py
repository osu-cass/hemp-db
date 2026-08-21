from pathlib import Path
from dotenv import load_dotenv
import os
import ssl
import dj_database_url
import sentry_sdk

from hempdb.csp import build_csp_directives, validate_report_uri

load_dotenv()


def env_value(name, default=None):
    """Read an environment value or its Docker secret file."""
    file_path = os.getenv(f'{name}_FILE')
    if file_path:
        try:
            return Path(file_path).read_text().strip()
        except OSError as error:
            raise RuntimeError(f'Unable to read {name}_FILE: {error}') from error

    return os.getenv(name, default)


def env_bool(name, default=False):
    """Read a boolean environment variable using common true values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    """Read an integer environment variable."""
    return int(os.getenv(name, str(default)))


def env_float(name, default):
    """Read a floating-point environment variable."""
    return float(os.getenv(name, str(default)))


def env_list(name, default=()):
    """Read a comma-separated environment variable."""
    value = os.getenv(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


def database_configuration(database_url, conn_max_age, use_ssl):
    """Build a Django database configuration from a resolved URL."""
    return dj_database_url.parse(
        database_url,
        conn_max_age=conn_max_age,
        ssl_require=use_ssl,
    )


def database_ssl_options(ca_path=''):
    """Build verified TLS options from an explicit or system CA store."""
    if ca_path:
        return {'ca': ca_path, 'check_hostname': True}

    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile:
        return {'ca': default_paths.cafile, 'check_hostname': True}
    if default_paths.capath:
        return {'capath': default_paths.capath, 'check_hostname': True}
    raise RuntimeError('A database CA file or system CA store is required for TLS.')


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
AUDIT_LOG_DIR = Path(
    os.getenv('AUDIT_LOG_DIR') or BASE_DIR / 'helloworld/management/commands/auditlogs'
)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env_value('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY or SECRET_KEY_FILE is required.')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DEBUG', False)

# Canonical public hostname
PRODUCTION_URL = os.getenv('PRODUCTION_URL', 'localhost')

default_allowed_hosts = ['localhost', '127.0.0.1', '[::1]'] if DEBUG else [PRODUCTION_URL]
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', default_allowed_hosts)
if not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS must contain at least one hostname.')

default_csrf_origins = [] if DEBUG else [f'https://{PRODUCTION_URL}']
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', default_csrf_origins)

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
if env_bool('TRUST_X_FORWARDED_PROTO', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

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
    'hempdb.apps.DjangoCronConfig',
    'csp',
]

SECURE_REFERRER_POLICY = 'same-origin'
PERMISSIONS_POLICY = 'camera=(), geolocation=(), microphone=(), payment=(), usb=()'

MIDDLEWARE = [
    'hempdb.middleware.PermissionsPolicyMiddleware',
    'django.middleware.security.SecurityMiddleware',
]
if not DEBUG:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
MIDDLEWARE += [
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
DATABASE_URL = env_value('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL or DATABASE_URL_FILE is required.')

DATABASE_SSL = env_bool('DATABASE_SSL', True)
DATABASES = {
    'default': database_configuration(
        DATABASE_URL,
        env_int('DATABASE_CONN_MAX_AGE', 600),
        DATABASE_SSL,
    )
}
DATABASES['default']['CONN_HEALTH_CHECKS'] = env_bool(
    'DATABASE_CONN_HEALTH_CHECKS', True
)
database_options = DATABASES['default'].setdefault('OPTIONS', {})
database_options['charset'] = 'utf8mb4'
database_options.pop('sslmode', None)
if DATABASE_SSL:
    database_ca_path = os.getenv('MYSQL_ATTR_SSL_CA', '').strip()
    database_options['ssl'] = database_ssl_options(database_ca_path)


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
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

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
SENTRY_DSN = env_value('SENTRY_DSN', '').strip()
SENTRY_ENVIRONMENT = os.getenv('SENTRY_ENVIRONMENT', 'production').strip() or 'production'
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=env_float('SENTRY_TRACES_SAMPLE_RATE', 0.1),
        profiles_sample_rate=env_float('SENTRY_PROFILES_SAMPLE_RATE', 0.0),
    )

# Configuration for sending emails
# https://docs.djangoproject.com/en/5.1/topics/email/
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.osuosl.org')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', not DEBUG)
EMAIL_HOST_USER = os.getenv('EMAIL_USER', '')
EMAIL_HOST_PASSWORD = env_value('EMAIL_APP_PASSWORD', '')
AUDIT_RECIPIENT = os.getenv('AUDIT_RECIPIENT', EMAIL_HOST_USER)
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    EMAIL_HOST_USER or 'webmaster@localhost',
)
EMAIL_LINK = os.getenv(
    'EMAIL_LINK',
    'http://localhost:8000' if DEBUG else f'https://{PRODUCTION_URL}',
)

REDIS_URL = env_value('REDIS_URL', '').strip()
if not REDIS_URL:
    raise RuntimeError('REDIS_URL or REDIS_URL_FILE is required.')
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
