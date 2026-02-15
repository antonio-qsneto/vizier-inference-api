"""
Django settings for vizier_backend project.
Production-ready SaaS configuration with AWS integration.
"""

import os
import logging
from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# SECURITY & ENVIRONMENT
# ============================================================================

SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-change-me')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# CORS Configuration
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv()
)

# ============================================================================
# APPLICATION DEFINITION
# ============================================================================

INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    'django_filters',
    
    # Local apps
    'apps.accounts.apps.AccountsConfig',
    'apps.tenants.apps.TenantsConfig',
    'apps.studies.apps.StudiesConfig',
    'apps.inference.apps.InferenceConfig',
    'apps.audit.apps.AuditConfig',
    'apps.health.apps.HealthConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'vizier_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'vizier_backend.wsgi.application'

# ============================================================================
# DATABASE
# ============================================================================

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DB_NAME', default=str(BASE_DIR / 'db.sqlite3')),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
    }
}

# Support for DATABASE_URL (e.g., postgresql://user:pass@host:5432/dbname)
if config('DATABASE_URL', default=None):
    import dj_database_url
    DATABASES['default'] = dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=600,
    )

# ============================================================================
# AUTHENTICATION & AUTHORIZATION
# ============================================================================

AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.auth.CognitoJWTAuthentication',
    'django.contrib.auth.backends.ModelBackend',
]

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

# ============================================================================
# REST FRAMEWORK
# ============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.accounts.auth.CognitoJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',  # Changed for development
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'vizier_backend.exceptions.custom_exception_handler',
}

# ============================================================================
# AWS CONFIGURATION
# ============================================================================

AWS_REGION = config('AWS_REGION', default='us-east-1')
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default=None)
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default=None)
S3_BUCKET = config('S3_BUCKET', default='vizier-med-results')

# ============================================================================
# COGNITO CONFIGURATION
# ============================================================================

COGNITO_REGION = config('COGNITO_REGION', default='us-east-1')
COGNITO_USER_POOL_ID = config('COGNITO_USER_POOL_ID', default=None)
COGNITO_CLIENT_ID = config('COGNITO_CLIENT_ID', default=None)

# Construct Cognito URLs from config
if COGNITO_USER_POOL_ID:
    COGNITO_ISSUER = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}'
    COGNITO_AUDIENCE = COGNITO_CLIENT_ID
    COGNITO_JWKS_URL = f'{COGNITO_ISSUER}/.well-known/jwks.json'
else:
    COGNITO_ISSUER = None
    COGNITO_AUDIENCE = None
    COGNITO_JWKS_URL = None

# JWT Cache (in-memory, use Redis for production)
COGNITO_JWT_CACHE_TIMEOUT = 3600  # 1 hour

# Development mode: disable authentication if Cognito not configured
DEVELOPMENT_MODE = not all([
    config('COGNITO_ISSUER', default=None),
    config('COGNITO_AUDIENCE', default=None),
    config('COGNITO_JWKS_URL', default=None),
])

# ============================================================================
# INFERENCE API
# ============================================================================

INFERENCE_API_URL = config('INFERENCE_API_URL', default='http://localhost:8000')
INFERENCE_API_TIMEOUT = 300  # 5 minutes
INFERENCE_POLL_INTERVAL = 5  # seconds

# ============================================================================
# DICOM PROCESSING
# ============================================================================

TEMP_DIR = config('TEMP_DIR', default='/tmp/vizier_med')
DICOM_TARGET_HW = (256, 256)
DICOM_TARGET_SLICES = 128
DICOM_WINDOW_CENTER = 40
DICOM_WINDOW_WIDTH = 400

# ============================================================================
# LOCAL ANALYSIS ARTIFACTS (DEV/DEBUG)
# ============================================================================

# When enabled, the backend will persist intermediate artifacts (e.g., original NPZ,
# mask NPZ, final NIfTI) to a local folder for debugging/investigation purposes.
# Keep disabled in production for LGPD/privacy-by-design.
SAVE_ANALYSIS_ARTIFACTS = config('SAVE_ANALYSIS_ARTIFACTS', default=DEBUG, cast=bool)
ANALYSIS_ROOT_DIR = config('ANALYSIS_ROOT_DIR', default='/tmp/vizier-analysis')

# ============================================================================
# STRIPE (PLACEHOLDER)
# ============================================================================

STRIPE_API_KEY = config('STRIPE_API_KEY', default=None)
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default=None)
ENABLE_STRIPE_BILLING = config('ENABLE_STRIPE_BILLING', default=False, cast=bool)

# ============================================================================
# FEATURE FLAGS
# ============================================================================

ENABLE_SEAT_LIMIT_CHECK = config('ENABLE_SEAT_LIMIT_CHECK', default=False, cast=bool)

# ============================================================================
# INTERNATIONALIZATION
# ============================================================================

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ============================================================================
# STATIC FILES
# ============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = config('LOG_LEVEL', default='INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}

# ============================================================================
# SECURITY SETTINGS (Production)
# ============================================================================

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
    }

# ============================================================================
# DEFAULT PRIMARY KEY
# ============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
