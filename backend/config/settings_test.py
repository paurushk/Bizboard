"""Test settings — in-memory SQLite by default, eager Celery, fast hashing.

BUG-712: SQLite doesn't meaningfully enforce SELECT ... FOR UPDATE locking,
so concurrency-sensitive tests (payment allocation, stock-oversell) would
pass here even with a real race bug, and only fail under real Postgres load.
Set DATABASE_URL (as CI now does) to run the suite against Postgres instead;
local `pytest` with no DATABASE_URL keeps the fast, zero-setup SQLite path.
"""

import os

# Local shells often export a Postgres DATABASE_URL that then deadlocks pytest
# when leftover clients hold the test DB. CI sets CI=1 and keeps DATABASE_URL.
# Opt back into local Postgres with PYTEST_KEEP_DATABASE_URL=1.
if not os.environ.get("CI") and os.environ.get("PYTEST_KEEP_DATABASE_URL") != "1":
    os.environ.pop("DATABASE_URL", None)
os.environ["DJANGO_ENV"] = "test"
# Force DEBUG on for tests (do not use setdefault — parent shells may export DJANGO_DEBUG=0).
os.environ["DJANGO_DEBUG"] = "1"
os.environ["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"

# BB-000313: must be set before importing settings when DJANGO_DEBUG=0.
os.environ.setdefault("OTP_PEPPER", "test-otp-pepper-not-for-prod")
os.environ.setdefault(
    "GSP_FERNET_KEY",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
)

from .settings import *  # noqa: E402,F401,F403

DJANGO_ENV = "test"

if not os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# Avoid requiring a live Redis for the test suite (login lockout uses cache).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bizboard-tests",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = BASE_DIR / "test_media"  # noqa: F405

OTP_DEBUG_ECHO = True
ENABLE_API_DOCS = True
ADMIN_ENABLED = True
ENABLE_MANUFACTURING = True
ENABLE_PAYROLL = True
ENABLE_CRM = True
ENABLE_TDS = True
ENABLE_GSTR = True
ENABLE_TALLY = True
# Fixture tenants (owner+staff, no plan) still invite in tests; production default is 1.
UNSUBSCRIBED_SEAT_LIMIT = 0
OTP_PEPPER = os.environ.get("OTP_PEPPER", "test-otp-pepper-not-for-prod")
GSP_FERNET_KEY = os.environ.get(
    "GSP_FERNET_KEY",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
)
