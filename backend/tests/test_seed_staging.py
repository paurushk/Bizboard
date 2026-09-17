"""Guards for seed_staging vs seed_pilot_fixtures environment policy."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import Company

pytestmark = pytest.mark.django_db


def test_seed_staging_refuses_development(settings):
    settings.DJANGO_ENV = "development"
    settings.DEBUG = True
    with pytest.raises(CommandError, match="only runs when DJANGO_ENV=staging"):
        call_command("seed_staging")


def test_seed_staging_refuses_production(settings):
    settings.DJANGO_ENV = "production"
    settings.DEBUG = False
    with pytest.raises(CommandError, match="only runs when DJANGO_ENV=staging"):
        call_command("seed_staging")


def test_seed_pilot_fixtures_still_refuses_staging(settings):
    settings.DJANGO_ENV = "staging"
    settings.DEBUG = False
    with pytest.raises(CommandError, match="refuses"):
        call_command("seed_pilot_fixtures")


def test_seed_staging_creates_c1_when_staging(settings):
    settings.DJANGO_ENV = "staging"
    settings.DEBUG = False
    call_command("seed_staging")
    assert Company.objects.filter(name="Pilot Retail GST").exists()
