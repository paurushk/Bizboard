"""SET-09b: the business pack shows what it will do and records that it did; opening cash is all-or-nothing."""

from accounts.models import CompanyPackState
from accounts.packs import PACKS, pack_preview
from core.models import AuditEvent

URL = "/api/v1/company/packs/"
COMPANY = "/api/v1/company/"
ANSWERS = {"what_you_sell": "rice", "how_you_sell": "counter", "deliver": "no", "gst_registered": "yes"}


def _on(tenant, flag):
    return bool((tenant.company.feature_flags or {}).get(flag))


def _set_flags(tenant, **changes):
    flags = dict(tenant.company.feature_flags or {})
    flags.update(changes)
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def _enable_packs(tenant):
    _set_flags(tenant, ENABLE_ARCHETYPE_PACKS=True)


def test_proposing_shows_what_confirming_would_do_and_changes_nothing(tenant_a):
    _enable_packs(tenant_a)
    before = dict(tenant_a.company.feature_flags)
    r = tenant_a.client.post(URL, {"answers": ANSWERS}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["applied"] is False and r.data["proposed_pack"] == "retail"
    preview = r.data["preview"]
    assert preview["pack"] == "retail"
    listed = (
        set(preview["would_enable"]) | set(preview["already_on"]) | set(preview["kept_as_set"]) | set(preview["unavailable"])
    )
    assert listed == set(PACKS["retail"])
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags == before


def test_preview_and_confirm_agree(tenant_a):
    _enable_packs(tenant_a)
    preview = tenant_a.client.post(URL, {"answers": ANSWERS}, format="json").data["preview"]
    done = tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    assert done.status_code == 200, done.data
    tenant_a.company.refresh_from_db()
    for key in preview["would_enable"]:
        assert _on(tenant_a, key), key
    assert sorted(done.data["skipped_flags"]) == sorted(preview["unavailable"])


def test_already_on_and_hand_set_flags_are_reported_and_kept(tenant_a):
    _enable_packs(tenant_a)
    first = PACKS["retail"][0]
    _set_flags(tenant_a, **{first: True})
    assert first in pack_preview(tenant_a.company, "retail")["already_on"]
    # Apply once, then someone switches a flag off by hand: the pack must not switch it back on.
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    tenant_a.company.refresh_from_db()
    second = next(k for k in PACKS["retail"] if _on(tenant_a, k) and k != first)
    _set_flags(tenant_a, **{second: False})
    assert second in pack_preview(tenant_a.company, "retail")["kept_as_set"]
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    tenant_a.company.refresh_from_db()
    assert not _on(tenant_a, second)


def test_applying_twice_changes_nothing_the_second_time(tenant_a):
    _enable_packs(tenant_a)
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    tenant_a.company.refresh_from_db()
    once = dict(tenant_a.company.feature_flags)
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags == once
    assert CompanyPackState.objects.filter(company=tenant_a.company).count() == 1


def test_a_pack_never_switches_anything_off(tenant_a):
    _enable_packs(tenant_a)
    _set_flags(tenant_a, ENABLE_CRM=True, SOME_OTHER_FLAG=True)
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags["SOME_OTHER_FLAG"] is True
    assert tenant_a.company.feature_flags["ENABLE_CRM"] is True


def test_confirming_is_audited_with_what_it_enabled(tenant_a):
    _enable_packs(tenant_a)
    preview = tenant_a.client.post(URL, {"answers": ANSWERS}, format="json").data["preview"]
    tenant_a.client.post(URL, {"answers": ANSWERS, "confirm": True}, format="json")
    event = AuditEvent.objects.get(company=tenant_a.company, action="pack.apply")
    assert event.metadata["pack"] == "retail" and event.user_id == tenant_a.owner.id
    assert sorted(event.metadata["enabled"]) == sorted(preview["would_enable"])


def test_the_pack_screen_is_owner_only_and_hidden_without_its_flag(tenant_a):
    assert tenant_a.client.post(URL, {"answers": ANSWERS}, format="json").status_code == 404
    _enable_packs(tenant_a)
    assert tenant_a.staff_client.post(URL, {"answers": ANSWERS}, format="json").status_code == 403


# ---- opening cash -------------------------------------------------------------------------------


def test_opening_cash_needs_both_a_balance_and_a_date(tenant_a):
    only_balance = tenant_a.client.patch(COMPANY, {"opening_cash_balance": "5000"}, format="json")
    assert only_balance.status_code == 400 and "opening_cash_as_of" in str(only_balance.data)
    only_date = tenant_a.client.patch(COMPANY, {"opening_cash_as_of": "2026-04-01"}, format="json")
    assert only_date.status_code == 400
    both = tenant_a.client.patch(
        COMPANY, {"opening_cash_balance": "5000", "opening_cash_as_of": "2026-04-01"}, format="json"
    )
    assert both.status_code == 200, both.data


def test_opening_cash_can_be_cleared_together_and_other_edits_are_unaffected(tenant_a):
    tenant_a.client.patch(COMPANY, {"opening_cash_balance": "5000", "opening_cash_as_of": "2026-04-01"}, format="json")
    assert tenant_a.client.patch(COMPANY, {"city": "Pune"}, format="json").status_code == 200
    cleared = tenant_a.client.patch(COMPANY, {"opening_cash_balance": None, "opening_cash_as_of": None}, format="json")
    assert cleared.status_code == 200, cleared.data
    assert tenant_a.client.patch(COMPANY, {"opening_cash_balance": "10"}, format="json").status_code == 400


def test_bill_scan_and_its_limit_cannot_be_changed_by_the_owner_through_the_company_api(tenant_a):
    """The AI screen shows these two as status only: the server ignores them from an owner."""
    before = (tenant_a.company.ai_features_enabled, tenant_a.company.ai_monthly_token_budget)
    r = tenant_a.client.patch(
        COMPANY, {"ai_features_enabled": not before[0], "ai_monthly_token_budget": 123456}, format="json"
    )
    assert r.status_code == 200
    tenant_a.company.refresh_from_db()
    assert (tenant_a.company.ai_features_enabled, tenant_a.company.ai_monthly_token_budget) == before
