"""pilot_metrics prints a table and does not invent a 5xx rate."""

from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_pilot_metrics_marks_5xx_as_not_instrumented(tenant_a):
    out = StringIO()
    call_command("pilot_metrics", stdout=out)
    text = out.getvalue()
    assert tenant_a.company.name in text
    assert "not instrumented" in text
    assert "Do not read the blank as zero" in text
