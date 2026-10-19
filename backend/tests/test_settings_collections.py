"""SET-17: reminders and automatic credit hold are saved from the Money-In rules endpoint."""

URL = "/api/v1/payments/money-in-rules/"


def test_collections_fields_are_in_the_rules_payload(tenant_a):
    r = tenant_a.client.get(URL)
    assert r.status_code == 200, r.data
    for key in (
        "dunning_enabled",
        "dunning_days",
        "dunning_max_reminders",
        "dunning_quiet_hours_start",
        "dunning_quiet_hours_end",
        "auto_credit_hold_on_severe_overdue",
    ):
        assert key in r.data, key


def test_saving_collections_rules_changes_only_those_and_leaves_cash_rules(tenant_a):
    before = tenant_a.client.get(URL).data
    r = tenant_a.client.patch(
        URL,
        {"dunning_enabled": True, "dunning_days": [14, 3, 7, 3], "dunning_max_reminders": 4,
         "dunning_quiet_hours_start": 20, "dunning_quiet_hours_end": 9, "auto_credit_hold_on_severe_overdue": True},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["dunning_enabled"] is True
    assert r.data["dunning_days"] == [3, 7, 14]
    assert r.data["dunning_max_reminders"] == 4
    assert r.data["auto_credit_hold_on_severe_overdue"] is True
    assert r.data["cash_269st_mode"] == before["cash_269st_mode"]
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.dunning_enabled is True


def test_cash_rule_save_does_not_touch_reminders(tenant_a):
    tenant_a.client.patch(URL, {"dunning_enabled": True, "dunning_days": [5]}, format="json")
    tenant_a.client.patch(URL, {"cash_269st_mode": "warn"}, format="json")
    data = tenant_a.client.get(URL).data
    assert data["dunning_enabled"] is True and data["dunning_days"] == [5]


def test_bad_values_are_refused_with_a_reason(tenant_a):
    for body in (
        {"dunning_days": [0]},
        {"dunning_days": [400]},
        {"dunning_days": ["x"]},
        {"dunning_days": "3,7"},
        {"dunning_max_reminders": 0},
        {"dunning_max_reminders": 11},
        {"dunning_quiet_hours_start": 24},
        {"dunning_quiet_hours_end": -1},
    ):
        r = tenant_a.client.patch(URL, body, format="json")
        assert r.status_code == 400, (body, r.status_code, r.data)


def test_staff_cannot_change_them(tenant_a):
    assert tenant_a.staff_client.patch(URL, {"dunning_enabled": True}, format="json").status_code == 403
