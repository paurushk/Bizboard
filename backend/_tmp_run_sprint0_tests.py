import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

import django

django.setup()

import pytest

raise SystemExit(
    pytest.main(
        [
            "tests/test_sprint0_security.py",
            "tests/test_auth.py::test_health_is_public",
            "-vv",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ]
    )
)
