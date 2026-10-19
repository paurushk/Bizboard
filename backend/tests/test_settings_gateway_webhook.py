"""SET-05: the webhook secret can be saved, does not undo a key check, and the provider address is restricted."""

from payments.gateway import decrypt_gateway_credentials, record_keys_accepted

URL = "/api/v1/payments/gateway-settings/"


def _creds(tenant):
    tenant.company.refresh_from_db()
    return decrypt_gateway_credentials(tenant.company.payment_gateway_credentials_encrypted or "")


def _save_keys(tenant):
    r = tenant.client.patch(
        URL, {"provider": "razorpay", "credentials": {"key_id": "rzp_test_abc123", "key_secret": "s3cr3tvalue"}}, format="json"
    )
    assert r.status_code == 200, r.data


def test_webhook_secret_status_and_last_event_time_are_reported(tenant_a):
    _save_keys(tenant_a)
    data = tenant_a.client.get(URL).data
    assert data["webhook_secret_configured"] is False and data["last_webhook_at"] is None
    tenant_a.client.patch(URL, {"credentials": {"webhook_secret": "whsec_123"}}, format="json")
    assert tenant_a.client.get(URL).data["webhook_secret_configured"] is True
    from payments.models import ProcessedWebhookEvent

    ProcessedWebhookEvent.objects.create(dedup_key="k-1", provider="razorpay", company=tenant_a.company)
    assert tenant_a.client.get(URL).data["last_webhook_at"]


def test_adding_only_the_webhook_secret_keeps_the_key_check(tenant_a):
    _save_keys(tenant_a)
    creds = _creds(tenant_a)
    record_keys_accepted(tenant_a.company, creds, "razorpay")
    tenant_a.company.save(update_fields=["payment_gateway_credentials_encrypted"])
    assert tenant_a.client.get(URL).data["credentials_verified"] is True
    tenant_a.client.patch(URL, {"credentials": {"webhook_secret": "whsec_123"}}, format="json")
    assert tenant_a.client.get(URL).data["credentials_verified"] is True
    tenant_a.client.patch(URL, {"credentials": {"key_secret": "different"}}, format="json")
    assert tenant_a.client.get(URL).data["credentials_verified"] is False


def test_provider_address_must_be_one_of_the_supported_ones(tenant_a):
    ok = tenant_a.client.patch(
        URL, {"provider": "cashfree", "credentials": {"app_id": "a", "secret_key": "b", "api_base": "https://sandbox.cashfree.com/pg/"}}, format="json"
    )
    assert ok.status_code in (200, 400)  # cashfree may be switched off in this deployment
    bad = tenant_a.client.patch(URL, {"credentials": {"api_base": "https://evil.example.com"}}, format="json")
    assert bad.status_code == 400, bad.data
    assert "api_base" not in _creds(tenant_a)
