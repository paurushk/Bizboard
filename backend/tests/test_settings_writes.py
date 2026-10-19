"""SET-11b: optimistic lock and idempotent create on settings endpoints (bank accounts first)."""

from datetime import timedelta

from payments.models import BankAccount

URL = "/api/v1/payments/bank-accounts/"


def _make(tenant):
    return BankAccount.objects.create(company=tenant.company, name="HDFC", is_default=True)


def _changed_elsewhere(account, name):
    """Simulate another owner's save, with a clearly later timestamp (auto_now is too coarse to rely on)."""
    BankAccount.objects.filter(pk=account.pk).update(
        name=name, updated_at=account.updated_at + timedelta(seconds=5)
    )


def test_update_with_current_updated_at_succeeds(tenant_a):
    account = _make(tenant_a)
    r = tenant_a.client.patch(
        f"{URL}{account.id}/",
        {"name": "HDFC Current", "expected_updated_at": account.updated_at.isoformat()},
        format="json",
    )
    assert r.status_code == 200, r.data
    account.refresh_from_db()
    assert account.name == "HDFC Current"


def test_update_with_stale_updated_at_is_refused_and_changes_nothing(tenant_a):
    account = _make(tenant_a)
    stale = account.updated_at.isoformat()
    _changed_elsewhere(account, "Changed by someone else")
    r = tenant_a.client.patch(
        f"{URL}{account.id}/", {"name": "Mine", "expected_updated_at": stale}, format="json"
    )
    assert r.status_code == 409, r.data
    account.refresh_from_db()
    assert account.name == "Changed by someone else"


def test_update_without_expected_updated_at_keeps_last_write_wins(tenant_a):
    account = _make(tenant_a)
    r = tenant_a.client.patch(f"{URL}{account.id}/", {"name": "Mine"}, format="json")
    assert r.status_code == 200, r.data


def test_update_with_header_form_of_the_lock(tenant_a):
    account = _make(tenant_a)
    stale = account.updated_at.isoformat()
    _changed_elsewhere(account, "Other")
    r = tenant_a.client.patch(
        f"{URL}{account.id}/", {"name": "Mine"}, format="json", HTTP_X_EXPECTED_UPDATED_AT=stale
    )
    assert r.status_code == 409


def test_bad_expected_updated_at_is_a_clear_400(tenant_a):
    account = _make(tenant_a)
    r = tenant_a.client.patch(
        f"{URL}{account.id}/", {"name": "Mine", "expected_updated_at": "yesterday"}, format="json"
    )
    assert r.status_code == 400


def test_create_with_same_idempotency_key_applies_once(tenant_a):
    body = {"name": "ICICI", "account_type": "CURRENT"}
    first = tenant_a.client.post(URL, body, format="json", HTTP_IDEMPOTENCY_KEY="key-set-11b-1")
    second = tenant_a.client.post(URL, body, format="json", HTTP_IDEMPOTENCY_KEY="key-set-11b-1")
    assert first.status_code == 201, first.data
    assert second.status_code in (200, 201), second.data
    assert BankAccount.objects.filter(company=tenant_a.company, name="ICICI").count() == 1
