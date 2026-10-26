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
PLANWAVE_RATE_LIMIT = os.environ.get(
    "PLANWAVE_RATE_LIMIT", "0" if DJANGO_ENV == "test" else "1",
) == "1"
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
# Local Compose staging is loopback HTTP (see docker-compose.staging.yml).
# Keep production-like fail-fast (no DEBUG, no SQLite, dedicated secrets) but
# allow localhost CORS/cookies so the SPA on 127.0.0.1 can sign in. A staging
# host with any non-local ALLOWED_HOSTS is treated as remote and unchanged.
_LOCAL_STAGING = DJANGO_ENV == "staging" and not _non_local_hosts
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
    "quality",
    "jobwork",
    "payroll",
    "crm",
    "complaints",
    "support",
    "contracts",
    "workshop",
    "projects",
    "insurance",
    "banking",
    "billing",
    "ops",
    "planwave",
    "agents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.MaxBodySizeMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestIdMiddleware",
    "core.middleware.AppVersionMiddleware",  # WP-L1
    "core.middleware.PublicLinkMiddleware",  # WP-AB4
    "core.middleware.PostgresRlsMiddleware",
    "billing.middleware.SubscriptionWriteGateMiddleware",
    "core.middleware.ContentSecurityPolicyMiddleware",  # QOS-0011
    "planwave.ratelimit.PlanRateLimitMiddleware",
]

CONTENT_SECURITY_POLICY = os.environ.get("CONTENT_SECURITY_POLICY")  # None -> middleware default
# WP-L1: oldest mobile app build (X-App-Version) the API still serves, e.g. "1.4.0". Empty = no floor.
MIN_SUPPORTED_APP_VERSION = os.environ.get("MIN_SUPPORTED_APP_VERSION", "").strip()
# WP-AB4: distinct networks one public share link may be opened from per day before it is flagged.
PUBLIC_LINK_SPREAD_LIMIT = _env_int("PUBLIC_LINK_SPREAD_LIMIT", 50)

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
        # DB_CONN_MAX_AGE=0 for `runserver`: it serves each request on a new thread, and every thread
        # would keep its own persistent connection until Postgres runs out of slots.
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
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
    _sqlite_opts = DATABASES["default"].setdefault("OPTIONS", {})
    _sqlite_opts["timeout"] = 30
    # A DEFERRED transaction that has already read hits SQLITE_BUSY_SNAPSHOT
    # the moment another connection commits (the shop-floor telemetry POST
    # does this during invoice/purchase complete). SQLite does not invoke the
    # busy handler for that code, so the 30s timeout never waits and complete
    # returns 500, leaving the document a draft. IMMEDIATE takes the write
    # lock at BEGIN so the other writer waits instead.
    _sqlite_opts["transaction_mode"] = "IMMEDIATE"

    def _sqlite_wal(sender, connection, **kwargs):
        if connection.vendor != "sqlite":
            return
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")

    from django.db.backends.signals import connection_created

    connection_created.connect(_sqlite_wal)
else:
    # CFG-05: reap dead pooled connections (needed with CONN_MAX_AGE > 0).
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# WP-5 (BB-068): behind PgBouncer (docker-compose.pgbouncer.yml) Django must not hold connections
# open; PgBouncer does the pooling, and a long-lived client connection pins a server connection.
DB_VIA_PGBOUNCER = _env_bool("DB_VIA_PGBOUNCER")
if DB_VIA_PGBOUNCER and DATABASES["default"].get("CONN_MAX_AGE"):
    raise ImproperlyConfigured(
        "DB_VIA_PGBOUNCER=1 needs DB_CONN_MAX_AGE=0 (PgBouncer pools the connections; "
        "see docs/ops/POSTGRES.md)."
    )
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

# Golden e2e registers and signs in once per spec. The production sign-up
# budgets (5/min) 429 that suite. Opt in only with DEBUG, so a deployed
# process cannot widen these limits by setting the env var alone.
_E2E_AUTH_THROTTLE = (
    "1000/min" if DEBUG and _env_bool("E2E_RELAX_AUTH_THROTTLE") else None
)
if _E2E_AUTH_THROTTLE:
    # Planwave counts every /auth/register* call, including OTP request, in a
    # 5/hour IP bucket. Golden signs up once per spec and would 429 after a
    # handful of tests. Same DEBUG gate as the DRF rates above.
    PLANWAVE_RATE_LIMIT = False

# Proxies in front of Django that append to X-Forwarded-For. The client is hop
# len(xff) - NUM_TRUSTED_PROXIES (from the right); everything left of it is
# client-supplied. Used by the login lock, planwave/ratelimit.py and, as
# REST_FRAMEWORK["NUM_PROXIES"], by every DRF throttle. nginx only = 1;
# Cloudflare tunnel or a provider LB in front of nginx = 2 (docs/ops/HOSTED_STAGING.md).
NUM_TRUSTED_PROXIES = _env_int("NUM_TRUSTED_PROXIES", 1)

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
    # Without this DRF keys anonymous throttles on the whole X-Forwarded-For
    # header, which the client controls: a fresh value per request is a fresh bucket.
    "NUM_PROXIES": NUM_TRUSTED_PROXIES,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "core.throttles.TenantPlanRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": _E2E_AUTH_THROTTLE or "120/min",
        "user": "600/min",
        "login": _E2E_AUTH_THROTTLE or "10/min",
        # UXW2-003: token refresh used to share "login"'s budget, but refresh
        # fires automatically (on 401 retry, on boot, on rapid navigation) and
        # isn't a credential-guessing surface (it requires an existing valid
        # httpOnly cookie, so a higher rate isn't a brute-force risk) — it needs
        # a much looser budget than login's intentionally tight anti-brute-force
        # limit. Kept above the frontend's own MIN_REFRESH_INTERVAL_MS debounce
        # ceiling (~12/min) so a legitimately fast-navigating user never trips it.
        "token_refresh": "60/min",
        # Sales Returns live total: one call per (debounced) edit, each a rolled-back transaction.
        "return_preview": "240/min",
        "otp": "5/min",
        # Separate from "otp" (which limits how many SMS get sent — an SMS
        # cost/abuse concern) — verifying a code should have its own,
        # slightly looser budget so it doesn't share a bucket with sending
        # and get exhausted by the OTP_MAX_ATTEMPTS=5 lockout path itself.
        "otp_verify": "20/min",
        "register": _E2E_AUTH_THROTTLE or "5/min",
        # Sign-up email verification code — same shape as "otp" (send budget).
        "register_otp": _E2E_AUTH_THROTTLE or "5/min",
        # D-19: the public referral-code check before sign-up.
        "referral_check": "30/min",
        # B6-012: tight budget for current-password verification (change-password
        # / delete-account) so a stolen short-lived access token can't brute-force it.
        "sensitive_action": "10/min",
        # WP-PO3: raising a platform support ticket (a P0/P1 pages on-call).
        "support_ticket": "10/hour",
        "accept_invite": "20/min",  # B6-025: onboarding-appropriate, own bucket
        "telemetry": "120/min",  # B9-032: shop-floor event ingest, own bucket
        # Per-company (CompanyRateThrottle) budgets for expensive reports.
        "gst_reports": "30/min",
        # Money In: a bulk CSV is heavy, and the totals are polled by the screen.
        "receipts_export": "20/hour",
        "receipts_summary": "120/min",
        # Customers master: paid GSP lookups, the full-party-master CSV, and the polled summary strip.
        "gstin_verify": "30/hour",
        "gstin_verify_user": "15/hour",
        "gstin_verify_bulk": "3/hour",
        "customers_export": "20/hour",
        "customers_summary": "120/min",
        "heavy_reports": "60/min",
        # B3-009: LLM bill-photo extraction has real per-call token cost;
        # cap how often a company can kick off a new extraction (upload or
        # retry) independent of the monthly token budget check in
        # extract_purchase_bill_task.
        "llm_bill_extraction": "30/hour",
        "search": "60/min",
        "help_events": "30/min",
        "help_feedback": "20/min",
        "password_reset": "5/min",
        "password_reset_confirm": "20/min",
        "tenant_api": "10000/min",
        # D-11 (2026-10-24): 60 Completes per minute per company, room for 2-3 busy counters.
        "sales_complete": "60/min",
        "purchase_complete": "30/min",
        "customer_portal_request": "5/min",
        "customer_portal_read": "60/min",
        "customer_portal_complaint": "10/hour",
        "public_pay": "20/min",
        "lead_form": "20/min",
        "whatsapp_webhook": "120/min",
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

# A refresh token rotated this many seconds ago is accepted once more from the same live device
# session: a page reload that aborts the refresh response otherwise signs the user out, because
# the browser never stored the rotated cookie. 0 turns the grace off. Signed-out or revoked
# sessions never qualify (accounts/user_sessions.py session_for_rotation_grace).
REFRESH_REUSE_GRACE_SECONDS = max(0, int(os.environ.get("REFRESH_REUSE_GRACE_SECONDS", "20")))

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
    # Supplier payments and advance refunds share the same two states (POSTED, VOIDED). Without this
    # the generator names the pair by hash ("Status51dEnum") and drops SupplierPaymentStatusEnum.
    "ENUM_NAME_OVERRIDES": {
        "SupplierPaymentStatusEnum": "payments.models.SupplierPaymentStatus",
    },
}

def _with_loopback_companions(origins: list[str]) -> list[str]:
    """Pair localhost ↔ 127.0.0.1 so cookie CSRF works on either host in non-prod.

    Playwright and some browsers use 127.0.0.1 while .env lists localhost (or
    the reverse). CSRF_TRUSTED_ORIGINS is an exact Origin match — missing the
    companion 403s cookie refresh after a full page load and the SPA boots
    logged-out.
    """
    seen = list(origins)
    extras: list[str] = []
    for origin in origins:
        companion = None
        if "://localhost" in origin:
            companion = origin.replace("://localhost", "://127.0.0.1", 1)
        elif "://127.0.0.1" in origin:
            companion = origin.replace("://127.0.0.1", "://localhost", 1)
        if companion and companion not in seen:
            seen.append(companion)
            extras.append(companion)
    return origins + extras


_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
if not CORS_ALLOWED_ORIGINS and DJANGO_ENV not in ("production", "staging"):
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
if DJANGO_ENV not in ("production", "staging"):
    CORS_ALLOWED_ORIGINS = _with_loopback_companions(CORS_ALLOWED_ORIGINS)
if DJANGO_ENV in ("production", "staging"):
    if not _cors_env.strip():
        raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be set in production/staging.")
    if not _LOCAL_STAGING and all("localhost" in o or "127.0.0.1" in o for o in CORS_ALLOWED_ORIGINS):
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
# Seconds the "is the GL usable as the outstanding figure" check is shared across
# requests (it runs three ledger aggregates). 0 disables the shared cache.
GL_BASIS_CACHE_SECONDS = _env_int("GL_BASIS_CACHE_SECONDS", 30)
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
# B7-002: a hung network call inside a task must not pin a worker slot forever.
# Soft limit raises SoftTimeLimitExceeded (catchable for cleanup); hard limit
# kills the worker process. Bill extraction is the known-long task — override
# per-task where needed.
CELERY_TASK_SOFT_TIME_LIMIT = _env_int("CELERY_TASK_SOFT_TIME_LIMIT", 600)
CELERY_TASK_TIME_LIMIT = _env_int("CELERY_TASK_TIME_LIMIT", 660)
# B7-002: bound the SMTP socket so send_email_notification can't block a worker.
EMAIL_TIMEOUT = _env_int("EMAIL_TIMEOUT", 10)
# BB-000234: explicit timezone for beat (Django TIME_ZONE is Asia/Kolkata).
# BB-000377: default beat TZ to Asia/Kolkata (matches Django TIME_ZONE).
# CFG-01: CELERY_ENABLE_UTC defaults False, so every crontab() below is
# interpreted in CELERY_TIMEZONE (Asia/Kolkata). All wall-clock comments here
# are therefore IST. (A previous comment claimed "06:00 IST ≈ 00:30 UTC" while
# the crontab said 00:30 — with enable_utc off that actually ran at 00:30 IST.)
# Bills priced under purchase cost are refused unless the company allows them or an owner
# records a reason (BUG-SALES-006). A company setting overrides this process default.
ALLOW_BELOW_COST_SALES_DEFAULT = _env_bool("ALLOW_BELOW_COST_SALES_DEFAULT")

# Hours a stock reservation stays before the beat task releases it. 0 (the default)
# means reservations never expire: a confirmed sales order holds its stock until it is
# delivered or cancelled. A company can opt in with feature_flags.reservation_ttl_hours.
STOCK_RESERVATION_TTL_HOURS = _env_int("STOCK_RESERVATION_TTL_HOURS", 0)
CELERY_TIMEZONE = os.environ.get("CELERY_TIMEZONE", "Asia/Kolkata")
CELERY_ENABLE_UTC = _env_bool("CELERY_ENABLE_UTC")
CELERY_BEAT_SCHEDULE = {
    # WP-PO2: weekly tenant health snapshot, fanned out per company (Monday 05:30 IST).
    "support-tenant-health-weekly": {
        "task": "support.tasks.tenant_health_weekly_task",
        "schedule": crontab(day_of_week=1, hour=5, minute=30),
    },
    # WP-ID4: revoke support access grants that ran out (only live grants).
    "support-expire-access-grants": {
        "task": "support.tasks.expire_support_access_task",
        "schedule": crontab(minute=5),
    },
    # WP-ID1: approved owner recoveries whose wait has passed (only those rows).
    "support-owner-recoveries": {
        "task": "support.tasks.complete_owner_recoveries_task",
        "schedule": crontab(minute=15),
    },
    # Monthly customer-master health check (stale GSTIN verification, state mismatches, duplicates).
    "masters-customers-audit-monthly": {
        "task": "masters.tasks.customers_audit_task",
        "schedule": crontab(day_of_month=1, hour=7, minute=30),
    },
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
    # DAN-06: the Attention feed is read-only; first-seen, snooze expiry, dismissal lapse and
    # resolved outcomes are stored here instead of on every GET.
    "insights-attention-sweep": {
        "task": "insights.tasks.sweep_attention_state_task",
        "schedule": crontab(minute="*/5"),
    },
    "accounting-monthly-depreciation": {
        # 00:05 IST on the 1st of the month.
        "task": "accounting.tasks.post_monthly_depreciation",
        "schedule": crontab(day_of_month=1, hour=0, minute=5),
    },
    # B8-005: near-expiry sweep + customer alerts (was a side effect of a GET).
    "inventory-expiry-bands": {
        "task": "inventory.tasks.record_expiry_bands_task",
        "schedule": crontab(hour=7, minute=0),
    },
    "sales-sweep-quotation-conversions": {
        "task": "sales.tasks.sweep_quotation_conversions",
        "schedule": crontab(hour=2, minute=30),
    },
    "sales-purge-old-invoice-zips": {
        "task": "sales.tasks.purge_old_invoice_zips_task",
        "schedule": crontab(hour=3, minute=15),
    },
    "inventory-release-expired-reservations": {
        "task": "inventory.tasks.release_expired_reservations_task",
        "schedule": crontab(minute="*/15"),
    },
    "reporting-itc-expiry-digest": {
        "task": "reporting.tasks.send_itc_expiry_digests_task",
        "schedule": crontab(hour=7, minute=30),
    },
    "crm-lead-activity-reminders": {
        "task": "crm.tasks.remind_due_lead_activities",
        "schedule": crontab(minute=40),
    },
    "crm-reap-stale-lead-ingest": {
        "task": "crm.tasks.reap_stale_lead_ingest_jobs",
        "schedule": crontab(minute="*/10"),
    },
    # Agents (AGT-113): one spec-driven dispatcher; each agent's schedule lives in its AgentSpec.
    "agents-dispatch-scheduled": {
        "task": "agents.tasks.dispatch_scheduled_agents",
        "schedule": crontab(minute="*/15"),
    },
    "agents-expire-proposals": {
        "task": "agents.tasks.expire_proposals",
        "schedule": crontab(minute="*/15"),
    },
    "agents-cancel-resolved": {
        "task": "agents.tasks.cancel_resolved",
        "schedule": crontab(minute=20),
    },
    "agents-purge-steps": {
        "task": "agents.tasks.purge_steps",
        "schedule": crontab(day_of_week="sun", hour=3, minute=45),
    },
    "celery-beat-heartbeat": {
        "task": "core.tasks.celery_beat_heartbeat",
        "schedule": crontab(minute="*/2"),
    },
    # Pages ops when the error tracker itself stops answering (no-op until ERROR_TRACKER_* is set).
    "core-check-error-tracker": {
        "task": "core.tasks.check_error_tracker_task",
        "schedule": crontab(minute="*/5"),
    },
    "contracts-refresh-status": {
        "task": "contracts.tasks.refresh_contract_statuses",
        "schedule": crontab(hour=1, minute=15),
    },
    "contracts-renewal-reminders": {
        "task": "contracts.tasks.send_contract_renewal_reminders",
        "schedule": crontab(hour=8, minute=30),
    },
    "projects-milestone-reminders": {
        "task": "projects.tasks.send_milestone_due_reminders",
        "schedule": crontab(hour=8, minute=45),
    },
    "sales-recurring-invoices": {
        "task": "sales.tasks.generate_recurring_invoices_task",
        "schedule": crontab(minute=15),
    },
    "sales-requeue-stale-pdfs": {
        "task": "sales.tasks.requeue_stale_invoice_pdfs",
        "schedule": crontab(minute="*/15"),
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
    # R-014: expired sandbox companies from tenant restore (wipe then delete).
    # SET-08: weekly encrypted backup for companies that opted in (Sunday, small hours).
    "accounts-scheduled-backups-weekly": {
        "task": "accounts.tasks.run_scheduled_backups_task",
        "schedule": crontab(day_of_week="sunday", hour=2, minute=15),
    },
    # SET-23: licence expiry, quiet gateway and plan-limit alerts to owners, once each.
    "accounts-settings-alerts-daily": {
        "task": "accounts.tasks.run_settings_alerts_task",
        "schedule": crontab(hour=7, minute=5),
    },
    # D-13: read-only workspaces - warnings 30/7 days ahead, erasure only with DATA_RETENTION_ENFORCE.
    "accounts-data-retention-daily": {
        "task": "accounts.tasks.apply_data_retention_task",
        "schedule": crontab(hour=4, minute=40),
    },
    # D-19 (BB-139): referred businesses that started paying.
    "billing-qualify-saas-referrals-daily": {
        "task": "billing.tasks.qualify_saas_referrals_task",
        "schedule": crontab(hour=5, minute=10),
    },
    "accounts-sweep-expired-sandboxes": {
        "task": "accounts.tasks.sweep_expired_sandboxes_task",
        "schedule": crontab(hour=4, minute=10),
    },
    "payments-ar-dunning": {
        "task": "payments.tasks.run_ar_dunning_task",
        "schedule": crontab(minute=20),
    },
    # 8.5 — SaaS PAST_DUE notices. Distinct from AR dunning above.
    "billing-saas-dunning": {
        "task": "billing.tasks.run_saas_dunning_task",
        "schedule": crontab(hour=8, minute=10),
    },
    # WP-DL1: delete readable export ZIPs whose 24-hour link ran out.
    "accounts-purge-readable-exports": {
        "task": "accounts.tasks.purge_readable_exports_task",
        "schedule": crontab(hour=3, minute=50),
    },
    # WP-BL3 / WP-BL4: undo unpaid upgrades; renewal reminder emails 3 days ahead.
    "billing-plan-change-renewals": {
        "task": "billing.tasks.plan_change_and_renewal_task",
        "schedule": crontab(hour=9, minute=5),
    },
    # WP-BL1: TDS credit on renewals the webhook missed; Form 16A reminders on the 16th.
    "billing-tds-credits-reminders": {
        "task": "billing.tasks.tds_credits_and_reminders_task",
        "schedule": crontab(hour=6, minute=40),
    },
    # 8.6 — Razorpay subscription GET vs local Subscription. Skips without keys.
    "billing-saas-recon": {
        "task": "billing.tasks.reconcile_saas_subscriptions_task",
        "schedule": crontab(minute=25),
    },
    "payments-gateway-holding-reconcile": {
        "task": "payments.tasks.reconcile_gateway_captures_task",
        "schedule": crontab(minute="*/5"),
    },
    # 5.6: owner/support recon — nightly invariant sweep (logs failures; command is the fail-closed gate).
    "core-nightly-invariants": {
        "task": "core.tasks.nightly_invariants_task",
        "schedule": crontab(hour=2, minute=20),
    },
    # F-SEC-03: seal new audit events into the hash chain, then verify it end to end.
    "core-seal-audit-chain": {
        "task": "core.tasks.seal_audit_chain_task",
        "schedule": crontab(hour=2, minute=40),
    },
}
# Coverage Copilot is a real, billed LLM call — off by default so it never
# starts spending money on a schedule without an explicit opt-in (the
# founder approved each manual run individually before this existed).
ENABLE_SCHEDULED_COVERAGE_AUDIT = _env_bool("ENABLE_SCHEDULED_COVERAGE_AUDIT", "0")
if ENABLE_SCHEDULED_COVERAGE_AUDIT:
    CELERY_BEAT_SCHEDULE["ops-coverage-audit-weekly"] = {
        "task": "ops.tasks.run_scheduled_coverage_audit",
        # 07:00 IST every Monday.
        "schedule": crontab(day_of_week=1, hour=7, minute=0),
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
# B7-012: opt-in debug echo — logs the PLAINTEXT OTP code at DEBUG level so a
# dev/CI can log in without SMS. Hard-rejected in production/staging (checked
# below); never enable it anywhere with real log shipping.
OTP_DEBUG_ECHO = _env_bool("OTP_DEBUG_ECHO")
# BB-000332: OTP enablement independent of debug echo (echo still forbidden in prod).
OTP_ENABLED = _env_bool("OTP_ENABLED")
# F1-011: same opt-in-debug-echo posture as OTP_DEBUG_ECHO, applied to the
# customer portal (COMP-003) magic-link token — a dev/e2e run can read the
# token straight from the request-link response instead of an inbox. Explicit
# switch, never implied by DEBUG/DJANGO_ENV (so an operator who leaves it off
# in a dev env is opting out of the leak, same rule as OTP). Hard-rejected in
# production/staging below.
PORTAL_DEBUG_ECHO = _env_bool("PORTAL_DEBUG_ECHO")
# Pepper for HMAC-SHA256 OTP storage; falls back to SECRET_KEY when unset (local only).
OTP_PEPPER = os.environ.get("OTP_PEPPER") or SECRET_KEY
# Default console stub; set SMS_PROVIDER=off to disable OTP in locked-down deploys.
SMS_PROVIDER = (os.environ.get("SMS_PROVIDER") or "console").strip().lower()
if DJANGO_ENV in ("production", "staging") and OTP_ENABLED and SMS_PROVIDER in ("", "console", "stub"):
    raise ImproperlyConfigured(
        "SMS_PROVIDER must be msg91 or twilio when OTP_ENABLED=1 in production/staging "
        "(or set SMS_PROVIDER=off and OTP_ENABLED=0)."
    )
# WP-AB1: caps in front of every SMS send (core/services/sms_guard.py). 0 = no cap.
# The per-phone hour cap matches the OTP view's own 5/hour limit; the guard also covers texts.
SMS_PER_PHONE_HOUR = _env_int("SMS_PER_PHONE_HOUR", 5)
SMS_PER_PHONE_DAY = _env_int("SMS_PER_PHONE_DAY", 10)
SMS_PER_RANGE_HOUR = _env_int("SMS_PER_RANGE_HOUR", 30)
SMS_RANGE_PREFIX_LEN = _env_int("SMS_RANGE_PREFIX_LEN", 4)
SMS_PLATFORM_DAILY_CAP = _env_int("SMS_PLATFORM_DAILY_CAP", 5000)
SMS_ALLOW_INTERNATIONAL = _env_bool("SMS_ALLOW_INTERNATIONAL")
SMS_DISABLED = _env_bool("SMS_DISABLED")
SMS_GUARD_FAIL_CLOSED = _env_bool("SMS_GUARD_FAIL_CLOSED", "1")
# WP-AB2: bot check on sign-up, OTP and reset (core/services/bot_check.py).
BOT_CHECK_PROVIDER = (os.environ.get("BOT_CHECK_PROVIDER") or "none").strip().lower()
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
# Comma-separated hostnames a Turnstile token must have been solved on (e.g. app.bizboard.in).
# Blank = not checked.
TURNSTILE_ALLOWED_HOSTNAMES = os.environ.get("TURNSTILE_ALLOWED_HOSTNAMES", "").strip()
BOT_CHECK_ENFORCE = _env_bool("BOT_CHECK_ENFORCE", "1")
BOT_CHECK_ALLOW_NONE = _env_bool("BOT_CHECK_ALLOW_NONE")
if BOT_CHECK_PROVIDER not in ("none", "stub", "turnstile"):
    # A typo would otherwise boot and then refuse every sign-up, OTP and reset at request time.
    raise ImproperlyConfigured(f"BOT_CHECK_PROVIDER={BOT_CHECK_PROVIDER!r} is not one of none, stub, turnstile.")
if DJANGO_ENV == "production" and BOT_CHECK_PROVIDER != "turnstile" and not BOT_CHECK_ALLOW_NONE:
    raise ImproperlyConfigured(
        "BOT_CHECK_PROVIDER must be 'turnstile' in production (sign-up and OTP are open to scripts "
        "otherwise). Set BOT_CHECK_ALLOW_NONE=1 to override deliberately."
    )
if BOT_CHECK_PROVIDER == "turnstile" and not TURNSTILE_SECRET_KEY:
    raise ImproperlyConfigured("TURNSTILE_SECRET_KEY is required when BOT_CHECK_PROVIDER=turnstile.")
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
    if not _LOCAL_STAGING and all("localhost" in o or "127.0.0.1" in o for o in CSRF_TRUSTED_ORIGINS):
        raise ImproperlyConfigured(
            "CSRF_TRUSTED_ORIGINS cannot be localhost-only in production/staging."
        )
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)
if DJANGO_ENV not in ("production", "staging"):
    CSRF_TRUSTED_ORIGINS = _with_loopback_companions(CSRF_TRUSTED_ORIGINS)

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
# B7-006: hard request-body ceiling enforced by MaxBodySizeMiddleware before the
# body is spooled. Above the largest legitimate upload (20 MB) + multipart
# overhead; the reverse proxy client_max_body_size is the other layer.
MAX_REQUEST_BODY_SIZE = int(
    os.environ.get("MAX_REQUEST_BODY_SIZE", str(25 * 1024 * 1024)) or (25 * 1024 * 1024)
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
    # B7-007: staging on HTTPS should also send HSTS (shorter max-age so a
    # mis-config is quick to roll back), not just production / USE_TLS.
    if DJANGO_ENV == "production" or _use_tls:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    elif DJANGO_ENV == "staging":
        SECURE_HSTS_SECONDS = 3600

if _LOCAL_STAGING and not _use_tls:
    # Browsers drop Secure cookies on plain HTTP. Remote staging (real hostname
    # or USE_TLS=1) still requires HTTPS cookies above.
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_SSL_REDIRECT = False

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

# F-SEC-02: TOTP secrets are Fernet-encrypted at rest. Comma-separated keys, newest first,
# allow rotation. Empty is allowed only in development and test; production and staging
# must set MFA_ENCRYPTION_KEY (BUG-SEC-014). Do not derive it from SECRET_KEY there.
# A reused Idempotency-Key with a different request body is rejected (422) instead of silently
# replaying the first response. Set IDEMPOTENCY_STRICT_FINGERPRINT=0 only to roll back quickly.
IDEMPOTENCY_STRICT_FINGERPRINT = _env_bool("IDEMPOTENCY_STRICT_FINGERPRINT", "1")
MFA_ENCRYPTION_KEY = os.environ.get("MFA_ENCRYPTION_KEY", "")
# AES-256-GCM key (url-safe base64 of 32 bytes) for bank account numbers and tax-portal secrets.
# Required in production and staging. planwave.crypto reads it from settings; without this line
# the setting never existed and every save of a bank number raised there.
PLANWAVE_DATA_KEY = os.environ.get("PLANWAVE_DATA_KEY", "")
# WP-B3: the id written into new sealed values (gcm1.<id>.<blob>), and older keys still readable,
# as "id:key,id:key". Rotation: set a new key and id, move the old one here, run
# rotate_encrypted_fields --apply, then remove it from this list.
PLANWAVE_DATA_KEY_ID = os.environ.get("PLANWAVE_DATA_KEY_ID", "k1").strip() or "k1"
PLANWAVE_RETIRED_KEYS = os.environ.get("PLANWAVE_RETIRED_KEYS", "")
# Where the nightly books-integrity failures are mailed (read by core.tasks).
OPS_ALERT_EMAIL = os.environ.get("OPS_ALERT_EMAIL", "")


def _assert_mfa_encryption_key(*, django_env: str, key: str) -> None:
    if django_env in ("production", "staging") and not (key or "").strip():
        raise ImproperlyConfigured(
            "MFA_ENCRYPTION_KEY is required when DJANGO_ENV is production or staging "
            "(do not derive it from SECRET_KEY)."
        )


def _assert_mfa_key_format(key: str) -> None:
    """A typo or a trimmed character must stop the boot, not surface as a 500 at first login."""
    from cryptography.fernet import Fernet

    for part in (key or "").split(","):
        if part.strip():
            try:
                Fernet(part.strip().encode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise ImproperlyConfigured("MFA_ENCRYPTION_KEY has a value that is not a valid Fernet key.") from exc


def _assert_planwave_data_key(*, django_env: str, key: str) -> None:
    import base64

    if not (key or "").strip():
        if django_env in ("production", "staging"):
            raise ImproperlyConfigured("PLANWAVE_DATA_KEY is required when DJANGO_ENV is production or staging.")
        return
    try:
        raw = base64.urlsafe_b64decode(key.strip() + "=" * (-len(key.strip()) % 4))
    except Exception as exc:  # noqa: BLE001
        raise ImproperlyConfigured("PLANWAVE_DATA_KEY is not url-safe base64.") from exc
    if len(raw) != 32:
        raise ImproperlyConfigured("PLANWAVE_DATA_KEY must decode to 32 bytes.")


def _assert_mfa_enforcement(*, django_env: str, enforce: bool, waiver: bool) -> None:
    """Env-only. Production or staging may turn enforcement off only with a waiver."""
    if django_env in ("production", "staging") and not enforce and not waiver:
        raise ImproperlyConfigured(
            "MFA_ENFORCE_FOR_MONEY_ROLES=0 in production or staging requires MFA_ENFORCE_WAIVER=1."
        )


def resolve_mfa_enforce(*, django_env: str, raw: str) -> bool:
    """Unset means on everywhere except an explicit test environment (BUG-SEC-004)."""
    if not (raw or "").strip():
        return django_env != "test"
    return _parse_debug_flag(raw)


_assert_mfa_encryption_key(django_env=DJANGO_ENV, key=MFA_ENCRYPTION_KEY)
_assert_mfa_key_format(MFA_ENCRYPTION_KEY)
_assert_planwave_data_key(django_env=DJANGO_ENV, key=PLANWAVE_DATA_KEY)
_mfa_enforce_raw = (os.environ.get("MFA_ENFORCE_FOR_MONEY_ROLES") or "").strip()
MFA_ENFORCE_FOR_MONEY_ROLES = resolve_mfa_enforce(django_env=DJANGO_ENV, raw=_mfa_enforce_raw)
MFA_ENFORCE_WAIVER = _env_bool("MFA_ENFORCE_WAIVER", "0")
_assert_mfa_enforcement(
    django_env=DJANGO_ENV,
    enforce=MFA_ENFORCE_FOR_MONEY_ROLES,
    waiver=MFA_ENFORCE_WAIVER,
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

# Agents (docs/roadmap/AGENTIC_AI_IMPLEMENTATION_PLAN_2026-10-21.md). Provider/model fall back to
# LLM_PROVIDER / LLM_MODEL. "fake" is the scripted provider used by tests and local dry runs.
LLM_AGENT_PROVIDER = _env_value("LLM_AGENT_PROVIDER")
LLM_AGENT_MODEL = _env_value("LLM_AGENT_MODEL")
# WP-H5 (DPDP): current versions of the legal documents a person accepts (accounts.legal). Counsel
# publishes the texts (G16); bump a version here and every user is asked to accept again at login.
LEGAL_DOCUMENT_VERSIONS = {
    "TOS": os.environ.get("LEGAL_TOS_VERSION", "draft-2026-10"),
    "PRIVACY": os.environ.get("LEGAL_PRIVACY_VERSION", "draft-2026-10"),
    "DPA": os.environ.get("LEGAL_DPA_VERSION", "draft-2026-10"),
}
LEGAL_ACCEPTANCE_REQUIRED = _env_bool("LEGAL_ACCEPTANCE_REQUIRED", "1")
AGENTS_GLOBAL_KILL = _env_bool("AGENTS_GLOBAL_KILL")
# WP-I1 (core/services/ai_spend.py): every model call reserves tokens against a daily company
# counter and a daily platform counter before it runs. 0 = no cap. AI_GLOBAL_KILL refuses every
# model call (assistant, bill reading, agents). Counters down -> refuse unless fail-open is chosen.
AI_GLOBAL_KILL = _env_bool("AI_GLOBAL_KILL")
AI_TENANT_DAILY_TOKEN_CAP = _env_int("AI_TENANT_DAILY_TOKEN_CAP", 300_000)
AI_PLATFORM_DAILY_TOKEN_CAP = _env_int("AI_PLATFORM_DAILY_TOKEN_CAP", 5_000_000)
AI_SPEND_FAIL_CLOSED = _env_bool("AI_SPEND_FAIL_CLOSED", "1")
AGENTS = {
    "MAX_STEPS": int(_env_value("AGENTS_MAX_STEPS", "6") or "6"),
    "MAX_TOOL_CALLS_PER_STEP": 3,
    "RUN_TIMEOUT_S": float(_env_value("AGENTS_RUN_TIMEOUT_S", "60") or "60"),
    "PER_RUN_TOKEN_CAP": int(_env_value("AGENTS_PER_RUN_TOKEN_CAP", "20000") or "20000"),
    "PER_COMPANY_DAILY_RUNS": int(_env_value("AGENTS_PER_COMPANY_DAILY_RUNS", "200") or "200"),
    "STEP_RETENTION_DAYS": 180,
}

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
# B6-006: a sandbox restore creates a full company copy of real tenant data --
# cap how many an owner can have live at once.
MAX_CONCURRENT_SANDBOXES = _env_int("MAX_CONCURRENT_SANDBOXES", 3)
# SET-08: restoring a backup OVER the live company deletes live data. Off unless support turns it on
# for a case; owners can only restore into a separate sandbox copy.
TENANT_RESTORE_DESTROY_ENABLED = _env_bool("TENANT_RESTORE_DESTROY_ENABLED", "0")
# BB-000726: PAST_DUE write grace after current_period_end (0 = block immediately).
BILLING_PAST_DUE_GRACE_DAYS = _env_int("BILLING_PAST_DUE_GRACE_DAYS", 0)
GSP_LIVE_ENABLED = _env_bool("GSP_LIVE_ENABLED")
# CBIC e-invoice turnover gate. Override without a code change when the threshold moves.
EINVOICE_AATO_THRESHOLD = os.environ.get("EINVOICE_AATO_THRESHOLD", "50000000")
# Stock-count variances at or under this quantity auto-post. Larger ones wait for review.
STOCK_COUNT_AUTO_POST_QTY = os.environ.get("STOCK_COUNT_AUTO_POST_QTY", "5")
# INV-WP-06: a count line worth at least this much (qty x purchase price) is flagged for a recheck.
STOCK_COUNT_RECHECK_VALUE = os.environ.get("STOCK_COUNT_RECHECK_VALUE", "10000")
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
    if PORTAL_DEBUG_ECHO:
        raise ImproperlyConfigured(
            f"PORTAL_DEBUG_ECHO must be disabled when DJANGO_ENV={DJANGO_ENV}."
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
    if any(k.strip().rstrip("=").replace("A", "") == "" for k in GSP_FERNET_KEY.split(",") if k.strip()):
        raise ImproperlyConfigured(
            "GSP_FERNET_KEY must not be the all-A placeholder from .env.example."
        )

# Optional Sentry (BB-000047 / BB-000360 / Wave 16A)
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", "").strip() or None
# The DSN the SPA was built with (VITE_SENTRY_DSN). core/error_tunnel.py forwards
# browser reports only to this project; empty = the tunnel answers 404.
SENTRY_BROWSER_DSN = os.environ.get("SENTRY_BROWSER_DSN", "").strip()
# Staff-only read access to the tracker (core/error_tracker.py): the admin errors
# page, Support ID links on tickets, and the tracker-down watcher. Empty = off.
ERROR_TRACKER_API_URL = os.environ.get("ERROR_TRACKER_API_URL", "").strip()
ERROR_TRACKER_UI_URL = os.environ.get("ERROR_TRACKER_UI_URL", "").strip()
ERROR_TRACKER_ORG = os.environ.get("ERROR_TRACKER_ORG", "bizboard").strip()
ERROR_TRACKER_TOKEN = os.environ.get("ERROR_TRACKER_TOKEN", "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        from core.observability import sentry_before_send

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
            environment=DJANGO_ENV,
            release=SENTRY_RELEASE,
            before_send=sentry_before_send,
        )
    except ImportError as exc:
        raise ImproperlyConfigured(
            "SENTRY_DSN is set but sentry-sdk is not installed."
        ) from exc

# Wave 16A — SMS gateway credentials (used when SMS_PROVIDER=msg91|twilio)
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "").strip()
MSG91_TEMPLATE_ID = os.environ.get("MSG91_TEMPLATE_ID", "").strip()
# WP-CM2: one DLT template ID per non-OTP SMS template (core/message_templates.py).
SMS_DLT_TEMPLATE_PAYMENT_REMINDER = os.environ.get("SMS_DLT_TEMPLATE_PAYMENT_REMINDER", "").strip()
MSG91_SENDER = os.environ.get("MSG91_SENDER", "BIZBRD").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

# SYS-01 — Postgres Row-Level Security (defense-in-depth tenant isolation).
# Migration core.0020 puts a company_id policy on every tenant table (FORCE RLS).
# Default OFF so development, empty DJANGO_ENV, the test suite, and SQLite keep
# booting. Production and staging on PostgreSQL refuse to start while this is
# off (BUG-SEC-019). Celery tenant context (BUG-SEC-001) is already in place.
# PostgresRlsMiddleware SETs app.company_id per request and clears GUCs afterwards.
POSTGRES_RLS_ENABLED = _env_bool("POSTGRES_RLS_ENABLED", "0")

# WP-F1: an unregistered posting source raises in tests (settings_test), is logged here.
LEDGER_REGISTRY_STRICT = False
LEDGER_TEST_SOURCE_TYPES: tuple[str, ...] = ()


def _assert_postgres_rls_required(*, django_env: str, engine: str, rls_enabled: bool) -> None:
    """Fail startup when production or staging uses PostgreSQL with RLS off.

    ``test``, ``development``, an empty ``DJANGO_ENV``, and any non-PostgreSQL
    engine (including SQLite) do not raise. This does not turn RLS on.
    """
    env = (django_env or "").strip().lower()
    if env not in ("production", "staging"):
        return
    eng = (engine or "").lower()
    if "postgresql" not in eng and "postgres" not in eng:
        return
    if rls_enabled:
        return
    raise ImproperlyConfigured(
        "POSTGRES_RLS_ENABLED must be on when DJANGO_ENV is production or staging "
        "and the database engine is PostgreSQL."
    )


_assert_postgres_rls_required(
    django_env=DJANGO_ENV,
    engine=_db_engine,
    rls_enabled=POSTGRES_RLS_ENABLED,
)
# Emergency rollback for R-002/R-003: set 0 to restore startswith("refund.") → REFUNDED.
PAYMENTS_REFUND_EVENT_MAP_V2 = _env_bool("PAYMENTS_REFUND_EVENT_MAP_V2", "1")
# R-019: COMPLETED docs older than this ISO date warn instead of blocking period close.
BOOKS_HEALTH_MISSING_POSTING_SINCE = (os.environ.get("BOOKS_HEALTH_MISSING_POSTING_SINCE") or "").strip()

# Wave 16C — GSP HTTP sandbox / live
GSP_HTTP_SANDBOX = _env_bool("GSP_HTTP_SANDBOX")
GSP_SANDBOX_BASE_URL = (os.environ.get("GSP_SANDBOX_BASE_URL") or "").rstrip("/")
IDENTITY_PROVIDER = (os.environ.get("IDENTITY_PROVIDER") or "null").strip().lower()
IDENTITY_SANDBOX_BASE_URL = (os.environ.get("IDENTITY_SANDBOX_BASE_URL") or "").rstrip("/")
FIU_BASE_URL = (os.environ.get("FIU_BASE_URL") or "").rstrip("/")
FIU_API_KEY = (os.environ.get("FIU_API_KEY") or "").strip()

# ClamAV host for the media upload scan. In production an unconfigured scanner
# is fail-open — FileService._clamav_scan refuses uploads unless CLAMAV_OPTIONAL
# is set (M1-012). The prod compose overlay ships a clamav service by default.
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "").strip()
CLAMAV_PORT = _env_int("CLAMAV_PORT", 3310)
CLAMAV_OPTIONAL = _env_bool("CLAMAV_OPTIONAL")

# Wave 17E — WhatsApp Cloud API (falls back to wa.me when unset)
WHATSAPP_TOKEN = _env_value("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env_value("WHATSAPP_PHONE_NUMBER_ID")

# Telegram bot notifications — single platform-wide bot, per-user chat_id linking.
TELEGRAM_BOT_TOKEN = _env_value("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = _env_value("TELEGRAM_BOT_USERNAME")
TELEGRAM_WEBHOOK_SECRET = _env_value("TELEGRAM_WEBHOOK_SECRET")

# Ops paging (no-infra PagerDuty/Sentry alternative): a fixed Telegram chat
# (e.g. a private on-call group) that Sentry alert rules / uptime monitors
# page via POST /api/v1/ops/alert/?token=<OPS_ALERT_TOKEN>. Uses the same bot
# as TELEGRAM_BOT_TOKEN above — this is not per-user, just one ops sink.
OPS_ALERT_TOKEN = _env_value("OPS_ALERT_TOKEN")
OPS_TELEGRAM_CHAT_ID = _env_value("OPS_TELEGRAM_CHAT_ID")
# Also push every ops page to this ntfy topic (https://ntfy.sh/<long random topic>, or a
# self-hosted ntfy): a free phone push next to, or instead of, the Telegram chat.
OPS_NTFY_URL = _env_value("OPS_NTFY_URL")

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
ENABLE_REPLENISHMENT = _env_bool("ENABLE_REPLENISHMENT")
ENABLE_GST_GUARD = _env_bool("ENABLE_GST_GUARD")
ENABLE_ROUTE_PROFIT = _env_bool("ENABLE_ROUTE_PROFIT")
ENABLE_SUPPLIER_PRICE_HISTORY = _env_bool("ENABLE_SUPPLIER_PRICE_HISTORY")
ENABLE_CUSTOMER_PORTAL = _env_bool("ENABLE_CUSTOMER_PORTAL")
ENABLE_ACTION_ASSIGNMENT = _env_bool("ENABLE_ACTION_ASSIGNMENT")
# D-13 (2026-10-25): erase read-only workspaces after their retention period. Off until counsel
# confirms the policy; while off the daily task only warns owners and logs what it would delete.
DATA_RETENTION_ENFORCE = _env_bool("DATA_RETENTION_ENFORCE")
# D-19 (BB-139): at most this many sign-ups per referral link per day are attributed.
SAAS_REFERRAL_DAILY_CAP = _env_int("SAAS_REFERRAL_DAILY_CAP", 20)
ENABLE_PREDICTIVE_DUNNING = _env_bool("ENABLE_PREDICTIVE_DUNNING")
ENABLE_CUSTOMER_360 = _env_bool("ENABLE_CUSTOMER_360", "1")  # on by default: founder decision 2026-10-11
# CUS-07: reject a customer whose GSTIN prefix disagrees with its state (and a changed phone that is
# not an Indian mobile). On by default (founder decision 2026-10-11); set CUSTOMER_STRICT_VALIDATION=0
# to relax. Existing rows are only checked when the field is edited. See `manage.py customers_audit`.
CUSTOMER_STRICT_VALIDATION = _env_bool("CUSTOMER_STRICT_VALIDATION", "1")
ENABLE_PURCHASE_PLANNING = _env_bool("ENABLE_PURCHASE_PLANNING")
ENABLE_ORDER_GATES = _env_bool("ENABLE_ORDER_GATES")
ENABLE_CUSTOMER_ACTIONS = _env_bool("ENABLE_CUSTOMER_ACTIONS")
ENABLE_CROSS_SELL = _env_bool("ENABLE_CROSS_SELL")
ENABLE_ROUTE_OPTIMIZATION = _env_bool("ENABLE_ROUTE_OPTIMIZATION")
ENABLE_CRM_WHATSAPP_INBOUND = _env_bool("ENABLE_CRM_WHATSAPP_INBOUND")
ENABLE_ARCHETYPE_PACKS = _env_bool("ENABLE_ARCHETYPE_PACKS")
ENABLE_COMPLAINTS = _env_bool("ENABLE_COMPLAINTS")
ENABLE_SUPPORT_TICKETS = _env_bool("ENABLE_SUPPORT_TICKETS")
ENABLE_CONTRACTS = _env_bool("ENABLE_CONTRACTS")
ENABLE_REFERRALS = _env_bool("ENABLE_REFERRALS")
ENABLE_WORKSHOP = _env_bool("ENABLE_WORKSHOP", "0")
ENABLE_PROJECTS = _env_bool("ENABLE_PROJECTS", "0")
ENABLE_INSURANCE = _env_bool("ENABLE_INSURANCE", "0")
# Empty means share-with-vendor returns 404 and writes no row.
VENDOR_COMPANY_ID = (os.environ.get("VENDOR_COMPANY_ID") or "").strip()
# Meta Cloud API app secret. Inbound webhooks are rejected when this is empty.
WHATSAPP_APP_SECRET = _env_value("WHATSAPP_APP_SECRET")
# Public lead form: most enquiries one company's form accepts in a day (a flood guard, not a quota).
LEAD_FORM_DAILY_CAP = int(os.environ.get("LEAD_FORM_DAILY_CAP") or 500)
# Shown under the public lead form. Wording needs sign-off from whoever owns privacy text.
LEAD_FORM_CONSENT_TEXT = os.environ.get("LEAD_FORM_CONSENT_TEXT") or (
    "By sending this form you agree that {company} may contact you about your enquiry."
)
ENABLE_WHATSAPP_CLOUD = _env_bool("ENABLE_WHATSAPP_CLOUD")
ENABLE_TELEGRAM = _env_bool("ENABLE_TELEGRAM")
ENABLE_ACCOUNT_AGGREGATOR = _env_bool("ENABLE_ACCOUNT_AGGREGATOR")
ENABLE_CASHFREE = _env_bool("ENABLE_CASHFREE")
ENABLE_PAYU = _env_bool("ENABLE_PAYU")
# Bizboard's own GSTIN and state for tenant subscription invoices. Blank GSTIN
# still produces the invoice; it is not treated as filed.
PLATFORM_GSTIN = _env_value("PLATFORM_GSTIN")
PLATFORM_STATE = _env_value("PLATFORM_STATE")
# WP-BL2: seller block on the PDF of Bizboard's own invoices.
PLATFORM_LEGAL_NAME = _env_value("PLATFORM_LEGAL_NAME") or "Bizboard"
# WP-ID5: Google OAuth web client id(s), comma-separated. Blank = Sign in with Google is off.
GOOGLE_OAUTH_CLIENT_IDS = _env_value("GOOGLE_OAUTH_CLIENT_IDS")
PLATFORM_ADDRESS = _env_value("PLATFORM_ADDRESS")
# WP-BL2: SAC on Bizboard's own GST invoices (CA to confirm; 998314 = IT design and development services).
PLATFORM_SAC_CODE = _env_value("PLATFORM_SAC_CODE") or "998314"
# WP-BL2: the daily recon only invoices Razorpay charges paid on or after this date (ISO, the day
# Bizboard started issuing its own GST invoices) and within the last 35 days. Blank = 35 days only.
PLATFORM_GST_INVOICES_FROM = _env_value("PLATFORM_GST_INVOICES_FROM")
# WP-CM1: HTTP Basic credentials the email provider uses on the bounce/complaint webhook
# (/api/v1/email/events/). Both blank = the webhook refuses every call.
EMAIL_WEBHOOK_USER = _env_value("EMAIL_WEBHOOK_USER")
EMAIL_WEBHOOK_PASSWORD = _env_value("EMAIL_WEBHOOK_PASSWORD")
# WP-AB3: one free trial per business (billing/trial_guard.py). Pepper: comma-separated, newest first.
TRIAL_FINGERPRINT_PEPPER = os.environ.get("TRIAL_FINGERPRINT_PEPPER", "")
TRIAL_DEDUPE_DAYS = _env_int("TRIAL_DEDUPE_DAYS", 365)
BLOCK_DISPOSABLE_EMAIL = _env_bool("BLOCK_DISPOSABLE_EMAIL", "1")
ENABLE_POS = _env_bool("ENABLE_POS")
ENABLE_SETUP_WIZARD = _env_bool("ENABLE_SETUP_WIZARD")
# Comma-separated company ids that always get Help v2 (internal / pilot).
HELP_V2_COMPANY_ALLOWLIST = os.environ.get("HELP_V2_COMPANY_ALLOWLIST", "")
# BB-000741: GSTR / Tally can unlock UI when VITE bake-off is false (CD).
ENABLE_GSTR = _env_bool("ENABLE_GSTR")
# Nav for GSTR-2B/4/6/7/8/9 worksheets. The frozen release shows GSTR-1 and 3B only;
# demo/staging turn this on (env ceiling, or a company grant).
ENABLE_GSTR_EXTENDED = _env_bool("ENABLE_GSTR_EXTENDED")
ENABLE_TALLY = _env_bool("ENABLE_TALLY")
# WP-GR1b: Busy / Vyapar / Marg one-time import; off, granted per pilot company (like Tally).
ENABLE_LEGACY_IMPORT = _env_bool("ENABLE_LEGACY_IMPORT")
ENABLE_GSTN_JSON = _env_bool("ENABLE_GSTN_JSON")
# Scope revision 2026-09-09b: D6 (fixed assets + depreciation) and D10 (Bill of
# Entry / import purchase + landed cost) are KNOWN LIMITATIONS. Default OFF so
# a copied production/staging env cannot inherit the old ON default. Tests opt
# in via settings_test; the pilot profile also pins 0. Route guards 404 them.
ENABLE_FIXED_ASSETS = _env_bool("ENABLE_FIXED_ASSETS", "0")
ENABLE_BOE = _env_bool("ENABLE_BOE", "0")
# D13 automated right-to-erasure. Default OFF — the owner-initiated erasure
# endpoint stays 404 until the founder signs off the statutory-retention
# carve-out (plan item SR-40). The completeness invariant + `erase_company`
# service ship regardless; only the HTTP surface is gated.
ENABLE_TENANT_ERASURE = _env_bool("ENABLE_TENANT_ERASURE", "0")
# D15 / QOS-0027: ARCH-05 statutory compliance (drug licence 20B/21B + FSSAI).
# Default OFF everywhere — this ships per-company ahead of a pharma/food pilot
# being provisioned; it has no effect on the ARCH-03 pilot's frozen scope.
ENABLE_ARCH05_STATUTORY_FORMS = _env_bool("ENABLE_ARCH05_STATUTORY_FORMS", "0")
# W0-03: park verified gateway captures when books cannot post. Off = fail webhook (emergency only).
# Default ON; set GATEWAY_HOLDING_STATE=0/false/no/off to disable (emergency only).
GATEWAY_HOLDING_STATE = _env_bool("GATEWAY_HOLDING_STATE", "1")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            # BB-048: secrets and personal data are masked in every line, tracebacks included.
            "()": "core.log_redaction.RedactingFormatter",
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
# WP-ID2: a user in more than one company must send X-Company-Id on every tenant API call
# (409 COMPANY_REQUIRED otherwise), so a header-less request never runs as the last-switched
# company. Off only as a quick rollback if a client is found that does not send the header.
REQUIRE_COMPANY_HEADER_FOR_MULTI = _env_bool("REQUIRE_COMPANY_HEADER_FOR_MULTI", "1")
