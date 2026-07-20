from pathlib import Path
from dotenv import load_dotenv
import os
import dj_database_url
import sentry_sdk

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', os.getenv('SECRET_KEY'))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['*']
PRODUCTION_URL = 'hempdb.vercel.app'  # TODO: change after infra migration

# For fetching datetime fields
USE_TZ = True       # Make datetime objects timezone-aware
TIME_ZONE = 'America/Los_Angeles'   # PST time, automatically handles daylight savings?  

OPTIONS = {
    'init_command': "SET time_zone='+00:00';"
}

INTERNAL_IPS = [
    "127.0.0.1",
]

# Logger config. Logs out all DB queries. Needs to be in DEBUG = True to log to console
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
        'level' : 'DEBUG'
    },
    'loggers': {
        'helloworld': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django-cron': {
            'handlers': ['mail_admins', 'console'],
            'level': 'ERROR',
            'propagate': True
        },
        # Fallback to catch any logging information that is not explicitly declared above
        '': {
            'handlers': ['console'],
            'level': 'DEBUG',
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
    'bootstrap5',
    'crispy_bootstrap5',
    'django_cron',
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_NAME', os.getenv('MYSQL_NAME')),
        'USER': os.environ.get('MYSQL_USER', os.getenv('MYSQL_USER')),
        'PASSWORD': os.environ.get('MYSQL_PASS', os.getenv('MYSQL_PASS')),
        'HOST': os.environ.get('MYSQL_HOST', os.getenv('MYSQL_HOST')),
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET time_zone = 'America/Los_Angeles';" # timezone conversion
        }
    }
}

DATABASES['default'] = dj_database_url.config(conn_max_age=600, ssl_require=True)
DATABASES['default']['OPTIONS']['charset'] = 'utf8mb4'
del DATABASES['default']['OPTIONS']['sslmode'] 
DATABASES['default']['OPTIONS']['ssl'] =  {'ca': os.environ.get('MYSQL_ATTR_SSL_CA')}


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
sentry_sdk.init(
    dsn=os.environ.get('SENTRY_DSN', os.getenv('SENTRY_DSN')),
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)

# Configuration for sending emails
# https://docs.djangoproject.com/en/5.1/topics/email/
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = DEFAULT_FROM_EMAIL = os.getenv('EMAIL_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_APP_PASSWORD')

if DEBUG: # Print emails to console instead of sending them
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    EMAIL_LINK = "http://localhost:8000"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_LINK = f"https://{PRODUCTION_URL}"

REDIS_URL = os.getenv('REDIS_URL').strip()
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
