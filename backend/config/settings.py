"""
Bizboard backend settings.

Local/dev/test fall back to SQLite; production supplies DATABASE_URL
(PostgreSQL) via environment. See .env.example.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-bizboard-secret-key-change-me-32b",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
DJANGO_ENV = (os.environ.get("DJANGO_ENV") or ("production" if not DEBUG else "development")).strip().lower()
_DEFAULT_SECRET = "dev-insecure-bizboard-secret-key-change-me-32b"
# Known placeholder values checked into this repo's own example env files —
# these must never be treated as "a real secret was set" (BUG-704). A prior
# length-only check (>=32 chars) let the .env.example placeholder through,
# since it happens to be 33 characters.
_KNOWN_PLACEHOLDER_SECRETS = {
    _DEFAULT_SECRET,
    "replace-with-a-long-random-secret",
    "replace-with-long-random-secret-at-least-32-chars",
    "change-me-in-production",
}
if DJANGO_ENV == "production" or os.environ.get("DJANGO_FAIL_FAST_SECRETS") == "1":
    if DEBUG:
        raise ImproperlyConfigured("DJANGO_DEBUG must be 0 in production.")
    if (
        not os.environ.get("DJANGO_SECRET_KEY")
        or SECRET_KEY in _KNOWN_PLACEHOLDER_SECRETS
        or len(SECRET_KEY) < 40
    ):
        raise ImproperlyConfigured(
            "Set a strong, unique DJANGO_SECRET_KEY (40+ chars, not a value copied "
            "from .env.example) for production."
        )
    if os.environ.get("REQUIRE_SMTP") == "1" and not os.environ.get("EMAIL_HOST"):
        raise ImproperlyConfigured("EMAIL_HOST is required when REQUIRE_SMTP=1.")
# NOTE (BUG-101, residual/documented risk): this check only fires once
# DJANGO_ENV resolves to "production", which itself derives from DEBUG when
# unset. An operator who deploys for real but simply never sets
# DJANGO_DEBUG=0 *at all* still boots with DEBUG=True and this check never
# runs — that specific gap can't be closed without either breaking the
# zero-config local-dev flow this repo's README documents, or requiring an
# explicit DJANGO_ENV=production in every real deployment (already done in
# .env.production.example; make sure any other deploy target does the same).
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    # Bizboard apps
    "core",
    "accounts",
    "masters",
    "inventory",
    "purchases",
    "sales",
    "payments",
    "imports",
    "ledgers",
    "reporting",
    "search",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: DATABASE_URL (PostgreSQL in prod) with SQLite fallback for local dev.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("core.renderers.EnvelopeJSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "djangorestframework_camel_case.parser.CamelCaseJSONParser",
        "djangorestframework_camel_case.parser.CamelCaseMultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "600/min",
        "login": "10/min",
        "otp": "5/min",
        # Separate from "otp" (which limits how many SMS get sent — an SMS
        # cost/abuse concern) — verifying a code should have its own,
        # slightly looser budget so it doesn't share a bucket with sending
        # and get exhausted by the OTP_MAX_ATTEMPTS=5 lockout path itself.
        "otp_verify": "20/min",
        "register": "5/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "JSON_UNDERSCOREIZE": {
        "no_underscore_before_number": True,
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Rotate on every refresh + blacklist the old token, so a stolen refresh
    # token used alongside the legitimate owner immediately desyncs and stops
    # working for one of them, rather than staying silently valid for the
    # full 7-day window (BUG-107).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bizboard API",
    "DESCRIPTION": "One-stop GST billing & business management platform — MVP API (v1).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# Celery
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True

# Email — console backend unless SMTP configured
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "billing@bizboard.local")

# OTP
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
# Echo OTP only when explicitly enabled AND DEBUG (never in production).
OTP_DEBUG_ECHO = DEBUG and os.environ.get("OTP_DEBUG_ECHO", "0") == "1"
# Default console stub; set SMS_PROVIDER=off to disable OTP in locked-down deploys.
SMS_PROVIDER = (os.environ.get("SMS_PROVIDER") or "console").strip().lower()
ENABLE_API_DOCS = os.environ.get("ENABLE_API_DOCS", "1") == "1"

# TLS / secure cookies when behind HTTPS terminator
if os.environ.get("USE_TLS", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = False  # terminate at nginx/load balancer

REFRESH_TOKEN_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "7"))
SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=REFRESH_TOKEN_DAYS)

def _env_value(key: str, default: str = "") -> str:
    """Read env var; strip whitespace and ignore values that are leftover inline comments."""
    raw = os.environ.get(key, default)
    if raw is None:
        return default
    value = str(raw).strip()
    if not value or value.startswith("#"):
        return default
    # Drop accidental "value # comment" if a host passed the whole line through
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    return value or default


# LLM — purchase bill / rate-list vision extraction
LLM_PROVIDER = _env_value("LLM_PROVIDER", "openai").lower()
OPENAI_API_KEY = _env_value("OPENAI_API_KEY")
DEEPSEEK_API_KEY = _env_value("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = _env_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
ANTHROPIC_API_KEY = _env_value("ANTHROPIC_API_KEY")
LLM_MODEL = _env_value("LLM_MODEL")
LLM_BILL_MAX_PAGES = int(_env_value("LLM_BILL_MAX_PAGES", "5") or "5")
