"""Phase A flag log: shape, and reserved keys must not overwrite the line."""

import pytest

from core.services.flag_observability import log_flag_event


@pytest.mark.django_db
def test_flag_event_logs_tenant_flag_and_state(tenant_a, caplog):
    log_flag_event(tenant_a.company, "ENABLE_GST_GUARD", "checked", check="format")
    assert "flag_event" in caplog.text
    assert f"tenant_id={tenant_a.company.id}" in caplog.text
    assert "flag=ENABLE_GST_GUARD" in caplog.text
    assert "event=checked" in caplog.text
    assert "check=format" in caplog.text


@pytest.mark.django_db
def test_flag_event_rejects_reserved_keys(tenant_a):
    with pytest.raises(ValueError):
        log_flag_event(tenant_a.company, "ENABLE_GST_GUARD", "checked", tenant_id=1)
    with pytest.raises(ValueError):
        log_flag_event(tenant_a.company, "ENABLE_GST_GUARD", "checked", flag_state="off")


def test_flag_and_event_are_named_params_not_reachable_via_fields(tenant_a):
    """`flag` and `event` are positional/named params on log_flag_event, so
    Python's own argument binding rejects a caller passing them as a
    **fields kwarg before the function body ever runs -- they must not be
    in _RESERVED, since a key that can never land in **fields can never
    need a reserved-key check."""
    with pytest.raises(TypeError):
        log_flag_event(tenant_a.company, "ENABLE_GST_GUARD", "checked", flag="ENABLE_OTHER")
    with pytest.raises(TypeError):
        log_flag_event(tenant_a.company, "ENABLE_GST_GUARD", "checked", event="other")
