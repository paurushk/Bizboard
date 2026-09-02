"""
Bizboard backend settings.

Local/dev/test fall back to SQLite; production supplies DATABASE_URL
(PostgreSQL) via environment. See .env.example.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-bizboard-secret-key-change-me-32b",
)


def _parse_debug_flag(raw: str | None) -> bool:
    """BB-000634: accept 1/true/yes/on (case-insensitive), not only literal '1'."""
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_bool(key: str, default: str = "0") -> bool:
    """One truthy convention for every boolean env flag: 1/true/yes/on (case-insensitive).

    Avoids the trap where ``ENABLE_POS=true`` was silently off because a call site
    only compared ``== "1"``. Falsy values (0/false/no/off/"") → False.
    """
    return _parse_debug_flag(os.environ.get(key, default))


def _env_int(key: str, default: int) -> int:
    """CFG-03: parse an int env var with a clear error naming the offending var
    instead of a bare ValueError from a stray ``int(os.environ[...])``.
    """
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"{key} must be an integer (got {raw!r})."
        ) from exc


# SEC-09: DEBUG is opt-in (default off). Local .env.example sets DJANGO_DEBUG=1.
DEBUG = _parse_debug_flag(os.environ.get("DJANGO_DEBUG", "0"))
# DJANGO_ENV is env-only (default development for local). Do not derive from DEBUG.
_DJANGO_ENV_EXPLICIT = "DJANGO_ENV" in os.environ
DJANGO_ENV = (os.environ.get("DJANGO_ENV") or "development").strip().lower()
# BB-000441: containers must set DJANGO_ENV explicitly (no silent development default).
if Path("/.dockerenv").exists() and "DJANGO_ENV" not in os.environ:
    raise ImproperlyConfigured(
        "DJANGO_ENV must be set explicitly inside containers "
        "(development|test|staging|production)."
    )
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
    "dev-only-change-me-long-random-secret-key-32chars",
}

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]


def _is_local_allowed_host(host: str) -> bool:
    h = host.strip().lower()
    # BB-000550: wildcard is never "local" — it bypasses DEBUG/ENV gates.
    return h in {"localhost", "127.0.0.1", "testserver"} or h.endswith(".localhost")


def _assert_allowed_hosts(hosts, django_env: str) -> None:
    if any(str(h).strip() == "*" for h in hosts) and django_env not in ("development", "test"):
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must not contain '*' outside development/test (BB-000550)."
        )


_assert_allowed_hosts(ALLOWED_HOSTS, DJANGO_ENV)


if any(not _is_local_allowed_host(h) for h in ALLOWED_HOSTS) and not _DJANGO_ENV_EXPLICIT:
    raise ImproperlyConfigured(
        "DJANGO_ENV must be set explicitly when ALLOWED_HOSTS includes hosts "
        "other than localhost / 127.0.0.1 / *.localhost."
    )

# BB-000249: refuse DEBUG on non-local hosts regardless of DJANGO_ENV label.
if DEBUG and DJANGO_ENV != "test" and any(not _is_local_allowed_host(h) for h in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_DEBUG must be 0 when ALLOWED_HOSTS includes non-local hosts."
    )

if DJANGO_ENV in ("production", "staging") or _env_bool("DJANGO_FAIL_FAST_SECRETS"):
    if DEBUG:
        raise ImproperlyConfigured(
            f"DJANGO_DEBUG must be 0 when DJANGO_ENV={DJANGO_ENV}."
        )
    if (
        not os.environ.get("DJANGO_SECRET_KEY")
        or SECRET_KEY in _KNOWN_PLACEHOLDER_SECRETS
        or len(SECRET_KEY) < 40
    ):
        raise ImproperlyConfigured(
            "Set a strong, unique DJANGO_SECRET_KEY (40+ chars, not a value copied "
            f"from .env.example) for {DJANGO_ENV}."
        )
    # Production/staging always require SMTP (REQUIRE_SMTP=1 kept as alias).
    if not os.environ.get("EMAIL_HOST"):
        raise ImproperlyConfigured(
            f"EMAIL_HOST is required when DJANGO_ENV={DJANGO_ENV} "
            "(invoice/share email must not use the console backend)."
        )

_non_local_hosts = any(not _is_local_allowed_host(h) for h in ALLOWED_HOSTS)
if not DEBUG and _non_local_hosts and DJANGO_ENV not in ("test",):
    if (
        not os.environ.get("DJANGO_SECRET_KEY")
        or SECRET_KEY in _KNOWN_PLACEHOLDER_SECRETS
        or len(SECRET_KEY) < 40
    ):
        raise ImproperlyConfigured(
            "Set a strong, unique DJANGO_SECRET_KEY (40+ chars) when DEBUG=0 and "
            "ALLOWED_HOSTS includes a non-local host."
        )

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
    "accounting",
    "search",
    "insights",
    "integrations",
    "manufacturing",
    "payroll",
    "crm",
    "banking",
    "billing",
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
    "core.middleware.RequestIdMiddleware",
    "core.middleware.PostgresRlsMiddleware",
    "billing.middleware.SubscriptionWriteGateMiddleware",
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
# BB-000544: production/staging must never silently fall back to SQLite.
_db_engine = (DATABASES["default"].get("ENGINE") or "").lower()
if DJANGO_ENV in ("production", "staging") and "sqlite" in _db_engine:
    raise ImproperlyConfigured(
        f"SQLite is not allowed when DJANGO_ENV={DJANGO_ENV}. "
        "Set DATABASE_URL to a PostgreSQL connection string."
    )
if "sqlite" in _db_engine:
    # CFG-06: persistent SQLite connections are a "database is locked" source
    # under the dev server + eager Celery; keep sqlite connections per-request.
    DATABASES["default"]["CONN_MAX_AGE"] = 0
else:
    # CFG-05: reap dead pooled connections (needed with CONN_MAX_AGE > 0).
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# BB-000546: Postgres statement / idle-in-transaction timeouts (ignored on SQLite).
if "postgresql" in _db_engine or "postgres" in _db_engine:
    _db_opts = DATABASES["default"].setdefault("OPTIONS", {})
    # libpq options string
    _extra = _db_opts.get("options", "")
    _timeouts = "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000"
    _db_opts["options"] = f"{_extra} {_timeouts}".strip() if _extra else _timeouts

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # R1-004: 10-char floor for an app that handles money (Django default is 8).
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    # BB-000497: local breached-password snippet; full HIBP k-anonymity is ops-owned.
    {"NAME": "accounts.password_validation.BreachedPasswordValidator"},
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
        "core.authentication.CookieJWTAuthentication",
        # BB-000547: Authorization Bearer disabled in production/staging (cookie-only).
        *(
            ()
            if DJANGO_ENV in ("production", "staging")
            else ("rest_framework_simplejwt.authentication.JWTAuthentication",)
        ),
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
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
        # UXW2-003: token refresh used to share "login"'s budget, but refresh
        # fires automatically (on 401 retry, on boot, on rapid navigation) and
        # isn't a credential-guessing surface (it requires an existing valid
        # httpOnly cookie, so a higher rate isn't a brute-force risk) — it needs
        # a much looser budget than login's intentionally tight anti-brute-force
        # limit. Kept above the frontend's own MIN_REFRESH_INTERVAL_MS debounce
        # ceiling (~12/min) so a legitimately fast-navigating user never trips it.
        "token_refresh": "60/min",
        "otp": "5/min",
        # Separate from "otp" (which limits how many SMS get sent — an SMS
        # cost/abuse concern) — verifying a code should have its own,
        # slightly looser budget so it doesn't share a bucket with sending
        # and get exhausted by the OTP_MAX_ATTEMPTS=5 lockout path itself.
        "otp_verify": "20/min",
        "register": "5/min",
        # Per-company (CompanyRateThrottle) budgets for expensive reports.
        "gst_reports": "30/min",
        "heavy_reports": "60/min",
        "search": "60/min",
        "help_events": "30/min",
        "help_feedback": "20/min",
        "password_reset": "5/min",
        "password_reset_confirm": "20/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "JSON_UNDERSCOREIZE": {
        "no_underscore_before_number": True,
        # Nested keys in this map are product field identifiers (brandCode), not
        # API field names. Recursing would turn them into brand_code and 400.
        "ignore_fields": ("custom_fields", "customFields"),
    },
}

SIMPLE_JWT = {
    # ACCESS_TOKEN_LIFETIME / REFRESH_TOKEN_LIFETIME are set below from
    # JWT_ACCESS_MINUTES (default 15m) and JWT_REFRESH_DAYS (default 7d). BB-000594.
    # Rotate on every refresh + blacklist the old token, so a stolen refresh
    # token used alongside the legitimate owner immediately desyncs and stops
    # working for one of them, rather than staying silently valid for the
    # full 7-day window (BUG-107).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bizboard API",
    "DESCRIPTION": (
        "Pilot GST billing, inventory, and derived ledgers API (v1). "
        "Not a full ERP — Manufacturing/Payroll/CRM are preview/dark, "
        "Tally HTTP is a one-shot export dump (not live sync), "
        "live NIC GSP submit is blocked, WhatsApp Cloud is optional per-tenant."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
if not CORS_ALLOWED_ORIGINS and DJANGO_ENV not in ("production", "staging"):
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
if DJANGO_ENV in ("production", "staging"):
    if not _cors_env.strip():
        raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be set in production/staging.")
    if all("localhost" in o or "127.0.0.1" in o for o in CORS_ALLOWED_ORIGINS):
        raise ImproperlyConfigured(
            "CORS_ALLOWED_ORIGINS cannot be localhost-only in production/staging."
        )
# Public SPA origin for payment links / share URLs (API and web are separate hosts in deploy).
FRONTEND_URL = (os.environ.get("FRONTEND_URL") or "").rstrip("/") or (
    CORS_ALLOWED_ORIGINS[0] if CORS_ALLOWED_ORIGINS else "http://localhost:5173"
)

_cors_regex_env = os.environ.get("CORS_ALLOWED_ORIGIN_REGEXES", "")
CORS_ALLOWED_ORIGIN_REGEXES = [r.strip() for r in _cors_regex_env.split(",") if r.strip()]
# BB-000258 / BB-000352: HMAC secret for sandbox payment webhooks.
SANDBOX_WEBHOOK_SECRET = (os.environ.get("SANDBOX_WEBHOOK_SECRET") or "").strip()
# BB-000318: sandbox provider is forbidden in production/staging (no settlement path).
# BB-000352: non-prod must set secret whenever sandbox could be used (dev/test templates).
if DJANGO_ENV in ("production", "staging"):
    pass  # sandbox banned at GatewaySettingsView; secret optional
elif DJANGO_ENV not in ("test",) and not SANDBOX_WEBHOOK_SECRET:
    # development: warn via empty — runtime BusinessRuleError if sandbox webhook fires.
    # Fail closed when explicitly required:
    if _env_bool("REQUIRE_SANDBOX_WEBHOOK_SECRET"):
        raise ImproperlyConfigured(
            "SANDBOX_WEBHOOK_SECRET is required when REQUIRE_SANDBOX_WEBHOOK_SECRET=1."
        )

# Celery / Redis
# REDIS_URL defaults to local Redis. CACHES prefer RedisCache whenever REDIS_URL
# is non-empty; for local without Redis, set REDIS_URL="" to fall back to LocMem
# (documented; Celery still expects a broker for non-eager workers).
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# BB-000250: LocMem lockout is unsafe multi-worker — require Redis in prod/staging.
if DJANGO_ENV in ("production", "staging") and not (REDIS_URL or "").strip():
    raise ImproperlyConfigured(
        f"REDIS_URL is required when DJANGO_ENV={DJANGO_ENV} (login lockout / Celery)."
    )
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bizboard-local",
        }
    }
CELERY_BROKER_URL = REDIS_URL or "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER")
# CFG-02: if an operator empties REDIS_URL to force the LocMem cache but does not
# also run tasks eagerly, every .delay() would silently fail against a
# non-existent localhost broker. Make that misconfiguration explicit.
if not (REDIS_URL or "").strip() and not CELERY_TASK_ALWAYS_EAGER and DJANGO_ENV != "test":
    raise ImproperlyConfigured(
        "REDIS_URL is empty but CELERY_TASK_ALWAYS_EAGER is not set — background "
        "tasks would fail silently. Set CELERY_TASK_ALWAYS_EAGER=1 for a "
        "broker-less local run, or provide REDIS_URL."
    )
CELERY_TASK_EAGER_PROPAGATES = True
# A down broker must fail fast instead of blocking Complete on the OS TCP timeout.
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 2,
    "socket_timeout": 2,
}
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 1,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.2,
}
# BB-000234: explicit timezone for beat (Django TIME_ZONE is Asia/Kolkata).
# BB-000377: default beat TZ to Asia/Kolkata (matches Django TIME_ZONE).
# CFG-01: CELERY_ENABLE_UTC defaults False, so every crontab() below is
# interpreted in CELERY_TIMEZONE (Asia/Kolkata). All wall-clock comments here
# are therefore IST. (A previous comment claimed "06:00 IST ≈ 00:30 UTC" while
# the crontab said 00:30 — with enable_utc off that actually ran at 00:30 IST.)
CELERY_TIMEZONE = os.environ.get("CELERY_TIMEZONE", "Asia/Kolkata")
CELERY_ENABLE_UTC = _env_bool("CELERY_ENABLE_UTC")
CELERY_BEAT_SCHEDULE = {
    "insights-daily-summaries": {
        "task": "insights.tasks.generate_daily_summaries_task",
        # 06:00 IST — start of the Indian business day.
        "schedule": crontab(hour=6, minute=0),
    },
    # BB-000636: daily summary already snapshots health — do not schedule a second job.
    "insights-cashflow-refresh": {
        "task": "insights.tasks.refresh_cashflow_forecasts_task",
        # 06:30 IST — right after the daily summary.
        "schedule": crontab(hour=6, minute=30),
    },
    "accounting-monthly-depreciation": {
        # 00:05 IST on the 1st of the month.
        "task": "accounting.tasks.post_monthly_depreciation",
        "schedule": crontab(day_of_month=1, hour=0, minute=5),
    },
    "celery-beat-heartbeat": {
        "task": "core.tasks.celery_beat_heartbeat",
        "schedule": crontab(minute="*/2"),
    },
    "sales-recurring-invoices": {
        "task": "sales.tasks.generate_recurring_invoices_task",
        "schedule": crontab(minute=15),
    },
    "payments-gateway-refund-outbox": {
        "task": "payments.tasks.retry_pending_gateway_refunds",
        "schedule": crontab(minute="*/5"),
    },
    "help-prune-events": {
        "task": "core.tasks.prune_help_events_task",
        "schedule": crontab(hour=3, minute=15, day_of_week=0),
    },
    # CORE-05: keep the durable Idempotency-Key table bounded (03:40 IST daily).
    "prune-idempotency-records": {
        "task": "core.tasks.prune_idempotency_records_task",
        "schedule": crontab(hour=3, minute=40),
    },
    "payments-ar-dunning": {
        "task": "payments.tasks.run_ar_dunning_task",
        "schedule": crontab(minute=20),
    },
    "payments-gateway-holding-reconcile": {
        "task": "payments.tasks.reconcile_gateway_captures_task",
        "schedule": crontab(minute="*/5"),
    },
}
AI_MONTHLY_TOKEN_BUDGET_DEFAULT = _env_int("AI_MONTHLY_TOKEN_BUDGET_DEFAULT", 100000)

# Email — console backend unless SMTP configured
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = _env_int("EMAIL_PORT", 587)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "billing@bizboard.local")

# OTP
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
# Opt-in debug echo (logs phone suffix only — never the code). Forbidden in
# production/staging (checked below).
OTP_DEBUG_ECHO = _env_bool("OTP_DEBUG_ECHO")
# BB-000332: OTP enablement independent of debug echo (echo still forbidden in prod).
OTP_ENABLED = _env_bool("OTP_ENABLED")
# Pepper for HMAC-SHA256 OTP storage; falls back to SECRET_KEY when unset (local only).
OTP_PEPPER = os.environ.get("OTP_PEPPER") or SECRET_KEY
# Default console stub; set SMS_PROVIDER=off to disable OTP in locked-down deploys.
SMS_PROVIDER = (os.environ.get("SMS_PROVIDER") or "console").strip().lower()
if DJANGO_ENV in ("production", "staging") and OTP_ENABLED and SMS_PROVIDER in ("", "console", "stub"):
    raise ImproperlyConfigured(
        "SMS_PROVIDER must be msg91 or twilio when OTP_ENABLED=1 in production/staging "
        "(or set SMS_PROVIDER=off and OTP_ENABLED=0)."
    )
# Docs off by default when not DEBUG; enable explicitly in locked-down envs if needed.
ENABLE_API_DOCS = _env_bool("ENABLE_API_DOCS", "1" if DEBUG else "0")
# Tally HTTP gateway URL for XML push adapter (optional).
TALLY_URL = os.environ.get("TALLY_URL", "")
METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")
# BB-000208: admin off by default outside DEBUG.
ADMIN_ENABLED = _env_bool("ADMIN_ENABLED", "1" if DEBUG else "0")
# BB-000625: credentials are always on for this app (cookie-JWT SPA), and the
# CORS spec forbids `Access-Control-Allow-Origin: *` together with credentials.
# CFG-04: the old CORS_ALLOW_ALL_ORIGINS env knob was therefore dead in every
# environment — turning it on only ever hard-crashed boot via the assert below.
# It is intentionally unsupported: use CORS_ALLOWED_ORIGINS (exact list) or
# CORS_ALLOWED_ORIGIN_REGEXES for local tooling instead.
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
if os.environ.get("CORS_ALLOW_ALL_ORIGINS"):
    raise ImproperlyConfigured(
        "CORS_ALLOW_ALL_ORIGINS is not supported (credentials are always on; the "
        "CORS spec forbids '*' with credentials). Set CORS_ALLOWED_ORIGINS or "
        "CORS_ALLOWED_ORIGIN_REGEXES instead."
    )


def _assert_cors_credentials_safe(*, origins, allow_all: bool, allow_credentials: bool) -> None:
    wildcard = bool(allow_all) or any(str(o).strip() == "*" for o in origins)
    if allow_credentials and wildcard:
        raise ImproperlyConfigured(
            "CORS wildcard (CORS_ALLOW_ALL_ORIGINS or '*') cannot be combined with "
            "credentials. Set explicit CORS_ALLOWED_ORIGINS."
        )


_assert_cors_credentials_safe(
    origins=CORS_ALLOWED_ORIGINS,
    allow_all=CORS_ALLOW_ALL_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
)

# BB-000602: SPA must read csrftoken for X-CSRFToken on cookie-JWT mutating calls.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")

# BB-000235: CSRF trusted origins from env; secure cookies in production.
_csrf_env = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_env.split(",") if o.strip()]
if DJANGO_ENV in ("production", "staging") and not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must be set in production/staging.")
if DJANGO_ENV in ("production", "staging") and CSRF_TRUSTED_ORIGINS:
    if all("localhost" in o or "127.0.0.1" in o for o in CSRF_TRUSTED_ORIGINS):
        raise ImproperlyConfigured(
            "CSRF_TRUSTED_ORIGINS cannot be localhost-only in production/staging."
        )
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

# Do not expand ALLOWED_HOSTS ".host" into CSRF/CORS wildcards — that would
# trust every subdomain of a tunnel/host suffix. Set CSRF_TRUSTED_ORIGINS explicitly.

# Trust X-Forwarded-Proto from reverse proxy (nginx / load balancer / Cloudflare tunnel)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CFG-05: cheap hardening headers for an app that serves user PDFs / photos.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get("SECURE_REFERRER_POLICY", "same-origin")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
# Error mail should not appear to come from root@localhost.
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
# Bill/rate-list photos are multipart uploads; raise the in-memory ceiling so a
# 10 MB DMS photo isn't spooled to a temp file on every request (still bounded).
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(15 * 1024 * 1024)) or (15 * 1024 * 1024)
)
FILE_UPLOAD_MAX_MEMORY_SIZE = int(
    os.environ.get("FILE_UPLOAD_MAX_MEMORY_SIZE", str(15 * 1024 * 1024)) or (15 * 1024 * 1024)
)

# TLS / secure cookies when behind HTTPS terminator, production, or staging (BB-000296).
_use_tls = _env_bool("USE_TLS")
if _use_tls or DJANGO_ENV in ("production", "staging"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # CFG-07: TLS is normally terminated at nginx / the load balancer, so the
    # app does not redirect by default. Set SECURE_SSL_REDIRECT=1 to opt in to
    # an app-level backstop when the edge is not trusted to do it.
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT")
    if DJANGO_ENV == "production" or _use_tls:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# BB-000257: refresh token in httpOnly cookie
JWT_REFRESH_COOKIE_NAME = os.environ.get("JWT_REFRESH_COOKIE_NAME", "bb_refresh")
JWT_ACCESS_COOKIE_NAME = os.environ.get("JWT_ACCESS_COOKIE_NAME", "bb_access")
JWT_REFRESH_COOKIE_PATH = "/api/v1/auth/"
JWT_ACCESS_COOKIE_PATH = "/"
JWT_REFRESH_COOKIE_SAMESITE = os.environ.get("JWT_REFRESH_COOKIE_SAMESITE", "Lax")
# BB-000353: SameSite=None without CSRF binding is forbidden (cross-site refresh mint).
if str(JWT_REFRESH_COOKIE_SAMESITE).lower() == "none" and os.environ.get(
    "JWT_REFRESH_ALLOW_SAMESITE_NONE", "0"
) != "1":
    raise ImproperlyConfigured(
        "JWT_REFRESH_COOKIE_SAMESITE=None requires JWT_REFRESH_ALLOW_SAMESITE_NONE=1 "
        "and a CSRF-protected refresh deploy. Prefer SameSite=Lax with same-site SPA/API."
    )

REFRESH_TOKEN_DAYS = _env_int("JWT_REFRESH_DAYS", 7)
SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=REFRESH_TOKEN_DAYS)
SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] = timedelta(minutes=_env_int("JWT_ACCESS_MINUTES", 15))

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
# Vision extract for purchase/sales bills. Unset → gpt-4o (mini cannot read
# 30×19 DMS photos). Chat/insights still use LLM_MODEL / gpt-4o-mini.
LLM_BILL_MODEL = _env_value("LLM_BILL_MODEL")
# Soft cap: pages actually rasterized/sent for extraction (batched in groups —
# see imports/tasks.py). Hard cap: reject outright, this is essentially never
# a genuine bill past this length (Bill Import Redesign Plan §7 Phase 3).
LLM_BILL_MAX_PAGES = int(_env_value("LLM_BILL_MAX_PAGES", "20") or "20")
LLM_BILL_MAX_PAGES_HARD = int(_env_value("LLM_BILL_MAX_PAGES_HARD", "50") or "50")

# GSP credential encryption (Fernet). If unset, derived from SECRET_KEY at use site.
GSP_FERNET_KEY = _env_value("GSP_FERNET_KEY")
# Tenant export wrapping key (BB-000668). Falls back to GSP_FERNET_KEY, then SECRET_KEY in local DEBUG/test.
TENANT_EXPORT_FERNET_KEY = _env_value("TENANT_EXPORT_FERNET_KEY")

# SaaS billing (BB-000671) — Razorpay subscriptions. Unset keys → stub checkout order ids.
RAZORPAY_KEY_ID = _env_value("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = _env_value("RAZORPAY_KEY_SECRET")
# When unset, webhook accepts only DJANGO_ENV=test (or DEBUG) with X-Bizboard-Test-Webhook: 1.
RAZORPAY_WEBHOOK_SECRET = _env_value("RAZORPAY_WEBHOOK_SECRET")
# BB-000725: block writes when company has no subscription (default off; on in production).
_require_sub = (os.environ.get("REQUIRE_SUBSCRIPTION") or "").strip().lower()
if _require_sub in ("1", "true", "yes"):
    REQUIRE_SUBSCRIPTION = True
elif _require_sub in ("0", "false", "no"):
    REQUIRE_SUBSCRIPTION = False
else:
    REQUIRE_SUBSCRIPTION = DJANGO_ENV == "production"
# No SaaS plan: starter seat (1), not unlimited. 0 = explicit unlimited.
UNSUBSCRIBED_SEAT_LIMIT = _env_int("UNSUBSCRIBED_SEAT_LIMIT", 1)
BILLING_TRIAL_DAYS = _env_int("BILLING_TRIAL_DAYS", 14)
# BB-000726: PAST_DUE write grace after current_period_end (0 = block immediately).
BILLING_PAST_DUE_GRACE_DAYS = _env_int("BILLING_PAST_DUE_GRACE_DAYS", 0)
GSP_LIVE_ENABLED = _env_bool("GSP_LIVE_ENABLED")
GSP_CERTIFIED = _env_bool("GSP_CERTIFIED")
_gsp_provider = (_env_value("GSP_PROVIDER", "custom") or "custom").strip().lower()
GSP_PROVIDER = _gsp_provider if _gsp_provider in ("cleartax", "mastergst", "custom") else "custom"
GSP_LIVE_BASE_URL = _env_value("GSP_LIVE_BASE_URL")

# Hardening for non-local deploy targets (after all related settings are defined).
# BB-000313: also refuse SECRET_KEY-derived OTP/Fernet when DEBUG=False.
_require_dedicated_secrets = DJANGO_ENV in ("production", "staging") or not DEBUG
if DJANGO_ENV in ("production", "staging"):
    if CELERY_TASK_ALWAYS_EAGER:
        raise ImproperlyConfigured(
            "CELERY_TASK_ALWAYS_EAGER must not be enabled when "
            f"DJANGO_ENV={DJANGO_ENV}."
        )
    if OTP_DEBUG_ECHO:
        raise ImproperlyConfigured(
            f"OTP_DEBUG_ECHO must be disabled when DJANGO_ENV={DJANGO_ENV}."
        )
if _require_dedicated_secrets:
    # BB-000226 / BB-000248 / BB-000313: dedicated secrets outside local DEBUG.
    if not os.environ.get("OTP_PEPPER"):
        raise ImproperlyConfigured(
            "OTP_PEPPER is required when DEBUG=False or "
            f"DJANGO_ENV={DJANGO_ENV} (do not derive from SECRET_KEY)."
        )
    if not GSP_FERNET_KEY:
        raise ImproperlyConfigured(
            "GSP_FERNET_KEY is required when DEBUG=False or "
            f"DJANGO_ENV={DJANGO_ENV} "
            "(do not rely on SECRET_KEY-derived Fernet keys)."
        )
    if GSP_FERNET_KEY.strip().rstrip("=").replace("A", "") == "":
        raise ImproperlyConfigured(
            "GSP_FERNET_KEY must not be the all-A placeholder from .env.example."
        )

# Optional Sentry (BB-000047 / BB-000360 / Wave 16A)
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", "").strip() or None
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            environment=DJANGO_ENV,
            release=SENTRY_RELEASE,
        )
    except ImportError as exc:
        raise ImproperlyConfigured(
            "SENTRY_DSN is set but sentry-sdk is not installed."
        ) from exc

# Wave 16A — SMS gateway credentials (used when SMS_PROVIDER=msg91|twilio)
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "").strip()
MSG91_TEMPLATE_ID = os.environ.get("MSG91_TEMPLATE_ID", "").strip()
MSG91_SENDER = os.environ.get("MSG91_SENDER", "BIZBRD").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

# SYS-01 — Postgres Row-Level Security (defense-in-depth tenant isolation).
# Migration core.0020 puts a company_id policy on every tenant table (FORCE RLS).
# Now ON by default; `PostgresRlsMiddleware` SETs app.company_id per request and
# clears every RLS GUC afterwards. No-op on SQLite. Stage on a Postgres replica
# / staging environment and soak before the prod cut-over; set
# POSTGRES_RLS_ENABLED=0 to fall back to app-level filtering only.
POSTGRES_RLS_ENABLED = _env_bool("POSTGRES_RLS_ENABLED", "1")

# Wave 16C — GSP HTTP sandbox / live
GSP_HTTP_SANDBOX = _env_bool("GSP_HTTP_SANDBOX")
GSP_SANDBOX_BASE_URL = (os.environ.get("GSP_SANDBOX_BASE_URL") or "").rstrip("/")
IDENTITY_PROVIDER = (os.environ.get("IDENTITY_PROVIDER") or "null").strip().lower()
IDENTITY_SANDBOX_BASE_URL = (os.environ.get("IDENTITY_SANDBOX_BASE_URL") or "").rstrip("/")
FIU_BASE_URL = (os.environ.get("FIU_BASE_URL") or "").rstrip("/")
FIU_API_KEY = (os.environ.get("FIU_API_KEY") or "").strip()

# Optional ClamAV host for media scan (compose profile clamav)
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "").strip()
CLAMAV_PORT = _env_int("CLAMAV_PORT", 3310)

# Wave 17E — WhatsApp Cloud API (falls back to wa.me when unset)
WHATSAPP_TOKEN = _env_value("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env_value("WHATSAPP_PHONE_NUMBER_ID")

# Wave 17F — payment gateway env credentials
CASHFREE_APP_ID = _env_value("CASHFREE_APP_ID")
CASHFREE_SECRET_KEY = _env_value("CASHFREE_SECRET_KEY")
CASHFREE_WEBHOOK_SECRET = _env_value("CASHFREE_WEBHOOK_SECRET")
PAYU_MERCHANT_KEY = _env_value("PAYU_MERCHANT_KEY")
PAYU_MERCHANT_SALT = _env_value("PAYU_MERCHANT_SALT")

# Wave 17G — runtime feature flags (merged with Company.feature_flags at API)
ENABLE_MANUFACTURING = _env_bool("ENABLE_MANUFACTURING")
ENABLE_PAYROLL = _env_bool("ENABLE_PAYROLL")
ENABLE_CRM = _env_bool("ENABLE_CRM")
ENABLE_TDS = _env_bool("ENABLE_TDS")
ENABLE_WHATSAPP_CLOUD = _env_bool("ENABLE_WHATSAPP_CLOUD")
ENABLE_ACCOUNT_AGGREGATOR = _env_bool("ENABLE_ACCOUNT_AGGREGATOR")
ENABLE_CASHFREE = _env_bool("ENABLE_CASHFREE")
ENABLE_PAYU = _env_bool("ENABLE_PAYU")
ENABLE_POS = _env_bool("ENABLE_POS")
ENABLE_SETUP_WIZARD = _env_bool("ENABLE_SETUP_WIZARD")
# Comma-separated company ids that always get Help v2 (internal / pilot).
HELP_V2_COMPANY_ALLOWLIST = os.environ.get("HELP_V2_COMPANY_ALLOWLIST", "")
# BB-000741: GSTR / Tally can unlock UI when VITE bake-off is false (CD).
ENABLE_GSTR = _env_bool("ENABLE_GSTR")
ENABLE_TALLY = _env_bool("ENABLE_TALLY")
ENABLE_GSTN_JSON = _env_bool("ENABLE_GSTN_JSON")
# W0-03: park verified gateway captures when books cannot post. Off = fail webhook (emergency only).
# Default ON; set GATEWAY_HOLDING_STATE=0/false/no/off to disable (emergency only).
GATEWAY_HOLDING_STATE = _env_bool("GATEWAY_HOLDING_STATE", "1")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            # CFG-08: timestamp so stdout capture is correlatable with the JSON
            # access log line emitted by RequestIdMiddleware.
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "bizboard.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# BB-000443: emit one JSON request line per response (see RequestIdMiddleware).
JSON_REQUEST_LOGS = _env_bool("JSON_REQUEST_LOGS", "1")

# D-01: multi-membership without active_company → 409 COMPANY_REQUIRED.
# Emergency: AUTO_PICK_COMPANY_ON_EMPTY=1 restores silent memberships[0].
# Forbidden in production/staging — wrong-tenant writes.
AUTO_PICK_COMPANY_ON_EMPTY = _env_bool("AUTO_PICK_COMPANY_ON_EMPTY")
if AUTO_PICK_COMPANY_ON_EMPTY and DJANGO_ENV in ("production", "staging"):
    raise ImproperlyConfigured(
        "AUTO_PICK_COMPANY_ON_EMPTY cannot be enabled when DJANGO_ENV is production or staging."
    )
