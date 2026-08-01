"""Test settings — in-memory SQLite by default, eager Celery, fast hashing.

BUG-712: SQLite doesn't meaningfully enforce SELECT ... FOR UPDATE locking,
so concurrency-sensitive tests (payment allocation, stock-oversell) would
pass here even with a real race bug, and only fail under real Postgres load.
Set DATABASE_URL (as CI now does) to run the suite against Postgres instead;
local `pytest` with no DATABASE_URL keeps the fast, zero-setup SQLite path.
"""

import os

from .settings import *  # noqa: F401,F403

if not os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = BASE_DIR / "test_media"  # noqa: F405

OTP_DEBUG_ECHO = True
