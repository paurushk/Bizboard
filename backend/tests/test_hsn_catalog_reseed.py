"""The HSN catalogue survives a flushing (transaction=True) test: tests/conftest.py puts it back."""

import pytest

from masters.models import HsnRate
from tests.conftest import _reseed_hsn_catalog

pytestmark = pytest.mark.django_db


def test_a_wiped_catalogue_is_seeded_again_as_the_migrations_left_it():
    before = set(HsnRate.objects.values_list("hsn_sac", "version", "rate"))
    assert ("3004", ) in {(h,) for h, _v, _r in before}
    HsnRate.objects.all().delete()
    _reseed_hsn_catalog()
    assert set(HsnRate.objects.values_list("hsn_sac", "version", "rate")) == before
