"""
Django settings for vizier_backend project.
Production-ready SaaS configuration with AWS integration.
"""

import ast
import os
import logging
from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _parse_hw_tuple(raw_value, default: tuple[int, int]) -> tuple[int, int]:
    """Parse width/height env values like '(512, 512)' or '512,512'."""
    if isinstance(raw_value, (tuple, list)) and len(raw_value) == 2:
        return (int(raw_value[0]), int(raw_value[1]))

    text = str(raw_value or '').strip()
    if not text:
        return default

    try:
        parsed = ast.literal_eval(text)
    except Exception:
        parsed = None

    if isinstance(parsed, (tuple, list)) and len(parsed) == 2:
        return (int(parsed[0]), int(parsed[1]))

    normalized = text.lower().replace('x', ',')
    parts = [part.strip() for part in normalized.split(',') if part.strip()]
    if len(parts) == 2:
        return (int(parts[0]), int(parts[1]))

    return default

# ============================================================================
# SECURITY & ENVIRONMENT
# ============================================================================

SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-change-me')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# CORS configuration for local frontend development.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default=(
        'http://localhost:3000,'
        'http://127.0.0.1:3000,'
        'http://localhost:5173,'
        'http://127.0.0.1:5173'
    ),
    cast=Csv(),
)
CORS_ALLOWED_ORIGIN_REGEXES = config(
    'CORS_ALLOWED_ORIGIN_REGEXES',
    default=(
        r'^https?://localhost(:\d+)?$,'
        r'^https?://127\.0\.0\.1(:\d+)?$,'
        r'^https?://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$,'
        r'^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$'
    ),
    cast=Csv(),
)

# ============================================================================
# EMAIL & INVITATIONS
# ============================================================================

EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default=(
        'django.core.mail.backends.console.EmailBackend'
        if DEBUG
        else 'django.core.mail.backends.smtp.EmailBackend'
    ),
)
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=not DEBUG, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@vizier.local')

INVITATION_PLATFORM_NAME = config('INVITATION_PLATFORM_NAME', default='Vizier Med')
INVITATION_LOGIN_URL = config('INVITATION_LOGIN_URL', default='http://localhost:3000/login')

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
        'rest_framework.permissions.IsAuthenticated',  # Changed for development
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
COGNITO_DOMAIN = config('COGNITO_DOMAIN', default=None)

# Construct Cognito URLs from config
if COGNITO_USER_POOL_ID:
    COGNITO_ISSUER = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}'
    COGNITO_AUDIENCE = COGNITO_CLIENT_ID
    COGNITO_JWKS_URL = f'{COGNITO_ISSUER}/.well-known/jwks.json'
else:
    COGNITO_ISSUER = None
    COGNITO_AUDIENCE = None
    COGNITO_JWKS_URL = None

if COGNITO_DOMAIN:
    COGNITO_TOKEN_URL = f'https://{COGNITO_DOMAIN}/oauth2/token'
    COGNITO_USERINFO_URL = f'https://{COGNITO_DOMAIN}/oauth2/userInfo'
else:
    # Primary explicit overrides.
    COGNITO_TOKEN_URL = config('COGNITO_TOKEN_URL', default=None)
    COGNITO_USERINFO_URL = config('COGNITO_USERINFO_URL', default=None)

    # Backwards-compatible env keys synced from Terraform (see scripts/sync_cognito_env_from_terraform.py).
    if not COGNITO_TOKEN_URL:
        COGNITO_TOKEN_URL = config('COGNITO_OAUTH_TOKEN_URL', default=None)
    if not COGNITO_USERINFO_URL:
        hosted_ui_base_url = config('COGNITO_HOSTED_UI_BASE_URL', default=None)
        if hosted_ui_base_url:
            COGNITO_USERINFO_URL = hosted_ui_base_url.rstrip('/') + '/oauth2/userInfo'

# JWT Cache (in-memory, use Redis for production)
COGNITO_JWT_CACHE_TIMEOUT = 3600  # 1 hour
COGNITO_JWT_LEEWAY_SECONDS = config('COGNITO_JWT_LEEWAY_SECONDS', default=60, cast=int)

# Development mode: disable authentication if Cognito not configured
DEVELOPMENT_MODE = not all([
    COGNITO_ISSUER,
    COGNITO_AUDIENCE,
    COGNITO_JWKS_URL,
])

# Optional local auth mode, independent from Cognito config.
DEV_MOCK_AUTH_ENABLED = config('DEV_MOCK_AUTH_ENABLED', default=DEBUG, cast=bool)
DEV_MOCK_TOKEN_MAX_AGE_SECONDS = max(
    60,
    config('DEV_MOCK_TOKEN_MAX_AGE_SECONDS', default=12 * 60 * 60, cast=int),
)

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
# Legacy spatial preprocessing knobs retained for backwards compatibility.
# The BiomedParse v2-aligned inference path preserves original shape and does
# not apply a backend-side resize/subsampling before creating input.npz.
DICOM_TARGET_HW = _parse_hw_tuple(config('DICOM_TARGET_HW', default='(512, 512)'), default=(512, 512))
DICOM_TARGET_SLICES = config('DICOM_TARGET_SLICES', default=64, cast=int)
DICOM_KEEP_ORIGINAL_SLICES = config('DICOM_KEEP_ORIGINAL_SLICES', default=True, cast=bool)
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
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default=STRIPE_API_KEY)
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default=None)
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default=None)
ENABLE_STRIPE_BILLING = config('ENABLE_STRIPE_BILLING', default=False, cast=bool)
STRIPE_PRODUCT_ID = config('STRIPE_PRODUCT_ID', default='prod_TwvQsWzxImOlIG')
STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY = config('STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY', default=None)
STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL = config('STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL', default=None)
STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_MONTHLY = config(
    'STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_MONTHLY',
    default=None,
)
STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_ANNUAL = config(
    'STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_ANNUAL',
    default=None,
)
STRIPE_PAYMENT_LINK_INDIVIDUAL_MONTHLY = config(
    'STRIPE_PAYMENT_LINK_INDIVIDUAL_MONTHLY',
    default='https://buy.stripe.com/test_cNicN755J5Ra3wwfvp5wI00',
)
STRIPE_PAYMENT_LINK_INDIVIDUAL_ANNUAL = config(
    'STRIPE_PAYMENT_LINK_INDIVIDUAL_ANNUAL',
    default='https://buy.stripe.com/test_9B6cN7eGja7q5EE0Av5wI01',
)

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
