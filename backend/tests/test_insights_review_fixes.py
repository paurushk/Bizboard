"""Regression tests for the Insights review fixes (INP-00 … INP-24)."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from insights.assistant import (
    ToolExecutor,
    _looks_like_tax_question,
    _pick_tools,
    confirm_proposed_action,
    run_assistant_turn,
)
from insights.models import AssistantMessage, AssistantThread, BusinessAlertEvent, DailyBusinessSummary
from insights.services import compute_health_score, forecast_cashflow, upsert_alerts
from masters.models import Customer, Supplier
from purchases.models import PurchaseInvoice


def _alert(company, code, severity, **kw):
    return BusinessAlertEvent.objects.create(
        company=company, code=code, severity=severity, message=f"{code} message", subject_key=kw.pop("subject_key", code), **kw,
    )


def _ap(tenant, amount, due_date):
    sup = Supplier.objects.get_or_create(company=tenant.company, name="AP Sup", defaults={"state": "Karnataka"})[0]
    return PurchaseInvoice.objects.create(
        company=tenant.company,
        supplier=sup,
        status=PurchaseInvoice.Status.COMPLETED,
        purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
        invoice_date=timezone.localdate() - timedelta(days=40),
        due_date=due_date,
        grand_total=Decimal(amount),
        created_by=tenant.owner,
    )


def _assistant_user(tenant, **flags):
    cu = CompanyUser.objects.get(company=tenant.company, user=tenant.staff)
    cu.can_use_ai_assistant = True
    cu.can_view_ai_insights = True
    for k, v in flags.items():
        setattr(cu, k, v)
    cu.save()
    return cu


# --------------------------------------------------------------------------- alerts (INP-04, INP-15)

@pytest.mark.django_db
def test_alerts_list_is_severity_first_not_newest_first(tenant_a):
    _alert(tenant_a.company, "OLD_CRITICAL", "critical")
    for i in range(6):
        _alert(tenant_a.company, f"NEW_INFO_{i}", "info")
    rows = tenant_a.client.get("/api/v1/insights/alerts/").data
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert rows[0]["code"] == "OLD_CRITICAL"


@pytest.mark.django_db
def test_snooze_is_attributed_audited_and_reversible(tenant_a):
    alert = _alert(tenant_a.company, "A1", "warning")
    resp = tenant_a.client.post(f"/api/v1/insights/alerts/{alert.id}/snooze/", {"days": 30}, format="json")
    assert resp.status_code == 200
    alert.refresh_from_db()
    assert alert.snoozed_by_id == tenant_a.owner.id
    assert alert.snoozed_at is not None
    assert AuditEvent.objects.filter(company=tenant_a.company, action="insights.alert.snoozed").exists()
    # Hidden from the open list, visible in the snoozed list.
    assert not _codes(tenant_a.client.get("/api/v1/insights/alerts/"))
    assert _codes(tenant_a.client.get("/api/v1/insights/alerts/?status=SNOOZED")) == ["A1"]
    back = tenant_a.client.post(f"/api/v1/insights/alerts/{alert.id}/unsnooze/", {}, format="json")
    assert back.status_code == 200
    assert _codes(tenant_a.client.get("/api/v1/insights/alerts/")) == ["A1"]
    assert AuditEvent.objects.filter(company=tenant_a.company, action="insights.alert.unsnoozed").exists()


def _codes(resp):
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    return [r["code"] for r in data]


@pytest.mark.django_db
def test_expired_snooze_reads_as_open_without_waiting_for_the_nightly_job(tenant_a):
    _alert(
        tenant_a.company, "EXPIRED", "warning",
        status=BusinessAlertEvent.Status.SNOOZED, snoozed_until=timezone.now() - timedelta(hours=1),
    )
    resp = tenant_a.client.get("/api/v1/insights/alerts/")
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert [(r["code"], r["status"]) for r in data] == [("EXPIRED", "OPEN")]


@pytest.mark.django_db
def test_snooze_rejects_a_bad_days_value_with_400(tenant_a):
    alert = _alert(tenant_a.company, "A2", "info")
    resp = tenant_a.client.post(f"/api/v1/insights/alerts/{alert.id}/snooze/", {"days": "soon"}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_only_one_live_alert_per_rule_and_subject(tenant_a):
    _alert(tenant_a.company, "DUP", "info", subject_key="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        _alert(tenant_a.company, "DUP", "warning", subject_key="x")
    # A resolved row does not block a new live one.
    BusinessAlertEvent.objects.filter(code="DUP").update(status=BusinessAlertEvent.Status.RESOLVED)
    _alert(tenant_a.company, "DUP", "warning", subject_key="x")


@pytest.mark.django_db
def test_margin_alerts_hidden_from_users_without_margin_access(tenant_a):
    _alert(tenant_a.company, "MARGIN_COMPRESSION", "warning")
    _alert(tenant_a.company, "AR_OVERDUE_WARN", "warning")
    cu = _assistant_user(tenant_a, can_view_financial_reports=True, role=CompanyUser.Role.MANAGER)
    assert cu.role == CompanyUser.Role.MANAGER
    assert set(_codes(tenant_a.staff_client.get("/api/v1/insights/alerts/"))) == {"AR_OVERDUE_WARN"}
    assert set(_codes(tenant_a.client.get("/api/v1/insights/alerts/"))) == {"MARGIN_COMPRESSION", "AR_OVERDUE_WARN"}


# --------------------------------------------------------------------------- summary (INP-06, INP-16, INP-18)

@pytest.mark.django_db
def test_daily_summary_get_never_writes_and_reports_staleness(tenant_a):
    first = tenant_a.client.get("/api/v1/insights/daily-summary/").data
    assert first["id"] is None and first["stale"] is True and first["can_generate"] is True
    assert DailyBusinessSummary.objects.count() == 0
    old = timezone.localdate() - timedelta(days=2)
    DailyBusinessSummary.objects.create(company=tenant_a.company, summary_date=old, narrative="old")
    got = tenant_a.client.get("/api/v1/insights/daily-summary/").data
    assert got["narrative"] == "old" and got["stale"] is True


@pytest.mark.django_db
def test_daily_summary_bad_date_is_400(tenant_a):
    assert tenant_a.client.get("/api/v1/insights/daily-summary/?date=junk").status_code == 400
    assert tenant_a.client.post("/api/v1/insights/daily-summary/", {"date": "junk"}, format="json").status_code == 400


@pytest.mark.django_db
def test_refresh_sends_nothing_and_digest_is_explicit(tenant_a):
    with patch("insights.services._maybe_send_digest_email") as email, patch(
        "insights.services._maybe_send_digest_whatsapp"
    ) as wa:
        assert tenant_a.client.post("/api/v1/insights/daily-summary/", {}, format="json").status_code == 200
        email.assert_not_called()
        wa.assert_not_called()
        assert tenant_a.client.post("/api/v1/insights/daily-summary/", {"send": True}, format="json").status_code == 200
        email.assert_called_once()
    assert AuditEvent.objects.filter(company=tenant_a.company, action="insights.summary.generated").exists()
    assert AuditEvent.objects.filter(company=tenant_a.company, action="insights.summary.digest_sent").exists()


@pytest.mark.django_db
def test_non_owner_cannot_generate(tenant_a):
    _assistant_user(tenant_a)
    resp = tenant_a.staff_client.post("/api/v1/insights/daily-summary/", {}, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_whatsapp_digest_is_held_back_until_its_template_exists(tenant_a):
    from insights import services

    summary = DailyBusinessSummary.objects.create(company=tenant_a.company, summary_date=timezone.localdate())
    with patch("core.services.notifications.NotificationService.send") as send:
        services._maybe_send_digest_whatsapp(tenant_a.company, summary, [])
        send.assert_not_called()


# --------------------------------------------------------------------------- cashflow (INP-03, INP-18)

@pytest.mark.django_db
def test_cashflow_horizon_validation(tenant_a):
    assert tenant_a.client.get("/api/v1/insights/cashflow-forecast/?horizon=abc").status_code == 400
    assert tenant_a.client.get("/api/v1/insights/cashflow-forecast/?horizon=5").status_code == 400
    assert tenant_a.client.get("/api/v1/insights/cashflow-forecast/?horizon=90").status_code == 200


@pytest.mark.django_db
def test_cashflow_bills_due_today_and_overdue_land_on_day_one(tenant_a):
    today = timezone.localdate()
    _ap(tenant_a, "1000", today)
    _ap(tenant_a, "2000", today - timedelta(days=10))
    _ap(tenant_a, "500", today + timedelta(days=3))
    cf = forecast_cashflow(tenant_a.company, horizon=7, as_of=today)
    assert Decimal(cf["series"][0]["outflow"]) == Decimal("3000.00")
    assert sum(Decimal(p["outflow"]) for p in cf["series"]) == Decimal("3500.00")
    assert cf["meta"]["overdue_payables"] == "3000.00"


@pytest.mark.django_db
def test_cashflow_range_is_ordered_even_when_cash_is_negative(tenant_a):
    today = timezone.localdate()
    _ap(tenant_a, "90000", today + timedelta(days=2))
    cf = forecast_cashflow(tenant_a.company, horizon=7, as_of=today)
    assert any(Decimal(p["ending_cash"]) < 0 for p in cf["series"])
    assert all(Decimal(p["low"]) <= Decimal(p["ending_cash"]) <= Decimal(p["high"]) for p in cf["series"])


@pytest.mark.django_db
def test_cashflow_baseline_rolls_forward_by_cleared_movements(tenant_a):
    from payments.models import CustomerReceipt, ReceiptStatus

    today = timezone.localdate()
    company = tenant_a.company
    company.opening_cash_balance = Decimal("10000")
    company.opening_cash_as_of = today - timedelta(days=10)
    company.save(update_fields=["opening_cash_balance", "opening_cash_as_of"])
    cust = Customer.objects.create(company=company, name="Payer", state="Karnataka")

    def receipt(amount, days_ago, **kw):
        return CustomerReceipt.objects.create(
            company=company, customer=cust, amount=Decimal(amount), mode=kw.pop("mode", "CASH"),
            status=ReceiptStatus.POSTED, receipt_date=today - timedelta(days=days_ago),
            created_by=tenant_a.owner, **kw,
        )

    receipt("2500", 3)                      # after the baseline: counts
    receipt("700", 20)                      # before the baseline: already in the balance
    receipt("900", 2, mode="CHEQUE")        # uncleared cheque: not cash yet
    cf = forecast_cashflow(company, horizon=7, as_of=today)
    assert cf["meta"]["starting_cash"] == "12500.00"
    assert cf["meta"]["recorded_since_baseline"] == "2500.00"


# --------------------------------------------------------------------------- health (INP-05, INP-13)

@pytest.mark.parametrize("overdue,expected", [("0", "100.00"), ("500", "50.00"), ("1000", "0.00")])
@pytest.mark.django_db
def test_payables_factor_falls_only_as_bills_go_overdue(tenant_a, overdue, expected):
    with patch("insights.services._open_payables_split", return_value=(Decimal("1000"), Decimal(overdue))):
        data = compute_health_score(tenant_a.company)
    factor = next(f for f in data["factors"] if f["key"] == "payables")
    assert factor["score"] == expected


@pytest.mark.django_db
def test_empty_company_withholds_the_grade_but_still_stores_a_score(tenant_a):
    from insights.services import snapshot_health

    data = compute_health_score(tenant_a.company)
    assert data["limited_data"] is True and data["grade_withheld"] is True
    snap = snapshot_health(tenant_a.company)
    assert snap.grade in "ABCDF" and snap.score is not None


@pytest.mark.django_db
def test_margin_factor_is_unavailable_without_costed_invoices_or_access(tenant_a):
    for include in (True, False):
        data = compute_health_score(tenant_a.company, include_margin=include)
        margin = next(f for f in data["factors"] if f["key"] == "margin")
        assert margin["available"] is False and margin["score"] is None
        # The score is re-weighted over the factors that exist, not dragged by a made-up value.
        assert Decimal(data["score"]) > 0


@pytest.mark.django_db
def test_compliance_failure_is_unavailable_not_fifty(tenant_a):
    with patch("reporting.gst_health.build_gst_health", side_effect=RuntimeError("boom")):
        data = compute_health_score(tenant_a.company)
    comp = next(f for f in data["factors"] if f["key"] == "compliance")
    assert comp["available"] is False and comp["score"] is None


@pytest.mark.django_db
def test_mtd_comparison_uses_the_same_day_range_of_the_prior_month(tenant_a):
    data = compute_health_score(tenant_a.company, as_of=timezone.localdate().replace(day=1) + timedelta(days=9))
    assert data["prior_month_range_end"].endswith("-10")


@pytest.mark.django_db
def test_health_history_hides_margin_factor_from_users_without_margin_access(tenant_a):
    from insights.services import snapshot_health

    snapshot_health(tenant_a.company)
    _assistant_user(tenant_a, can_view_financial_reports=True, role=CompanyUser.Role.MANAGER)
    rows = tenant_a.staff_client.get("/api/v1/insights/health/history/").data
    assert all(f["key"] != "margin" for r in rows for f in r["factors"])
    owner_rows = tenant_a.client.get("/api/v1/insights/health/history/").data
    assert any(f["key"] == "margin" for r in owner_rows for f in r["factors"])


# --------------------------------------------------------------------------- assistant: permissions and privacy (INP-02)

@pytest.mark.django_db
def test_assistant_tools_follow_the_data_permissions(tenant_a):
    cu = _assistant_user(tenant_a, can_view_financial_reports=False)
    ex = ToolExecutor(tenant_a.company, cu)
    for tool in ("get_receivables_aging", "get_payables_aging", "get_customer_outstanding",
                 "get_cashflow_forecast", "get_sales_totals", "get_health_score", "get_daily_summary"):
        with pytest.raises(BusinessRuleError, match="does not have access"):
            ex.run(tool, {})
    assert "alerts" in ex.run("list_business_alerts", {})  # insights permission is enough for alerts


@pytest.mark.django_db
def test_assistant_hides_margin_signals_without_margin_access(tenant_a):
    cu = _assistant_user(tenant_a, can_view_financial_reports=True, role=CompanyUser.Role.MANAGER)
    health = ToolExecutor(tenant_a.company, cu).run("get_health_score", {})
    assert next(f for f in health["factors"] if f["key"] == "margin")["available"] is False
    _alert(tenant_a.company, "MARGIN_DROP_SKU", "warning")
    alerts = ToolExecutor(tenant_a.company, cu).run("list_business_alerts", {})["alerts"]
    assert all(a["code"] != "MARGIN_DROP_SKU" for a in alerts)


@pytest.mark.django_db
def test_a_bad_tool_argument_does_not_crash_the_turn(tenant_a):
    ex = ToolExecutor(tenant_a.company, None)
    with pytest.raises(BusinessRuleError):
        ex.run("get_sales_totals", {"days": "many"})
    with pytest.raises(BusinessRuleError):
        ex.run("get_sales_totals", {"unexpected": 1})


@pytest.mark.django_db
def test_threads_are_private_to_their_creator(tenant_a):
    _assistant_user(tenant_a)
    mine = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner, title="owner chat")
    resp = tenant_a.staff_client.get("/api/v1/insights/assistant/threads/")
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert data == []
    assert tenant_a.staff_client.get(f"/api/v1/insights/assistant/threads/{mine.id}/").status_code == 404
    post = tenant_a.staff_client.post(
        f"/api/v1/insights/assistant/threads/{mine.id}/messages/", {"content": "hi"}, format="json",
    )
    assert post.status_code == 404


@pytest.mark.django_db
def test_other_users_cannot_confirm_or_dismiss_a_proposal(tenant_a):
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = AssistantMessage.objects.create(
        thread=thread, role="assistant", content="x",
        proposed_action={"type": "send_reminder", "text": "pay", "email": "a@b.co"},
    )
    with pytest.raises(BusinessRuleError, match="not found"):
        confirm_proposed_action(tenant_a.company, tenant_a.staff, msg.id)
    resp = tenant_a.staff_client.post("/api/v1/insights/assistant/actions/dismiss/", {"messageId": msg.id}, format="json")
    assert resp.status_code in (400, 403)
    msg.refresh_from_db()
    assert msg.proposed_action is not None


@pytest.mark.django_db
def test_sending_a_reminder_needs_the_reminder_permission(tenant_a):
    cu = _assistant_user(tenant_a, can_view_financial_reports=True, can_create_payments=False)
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.staff)
    msg = AssistantMessage.objects.create(
        thread=thread, role="assistant", content="x",
        proposed_action={"type": "send_reminder", "text": "pay", "email": "a@b.co"},
    )
    with pytest.raises(BusinessRuleError, match="not allowed"):
        confirm_proposed_action(tenant_a.company, tenant_a.staff, msg.id, cu=cu)


# --------------------------------------------------------------------------- assistant: confirm (INP-01)

def _reminder(tenant, **proposal):
    cust = Customer.objects.create(
        company=tenant.company, name="Pay Me", state="Karnataka", email=proposal.pop("email", "pay@ex.com"),
        phone=proposal.pop("phone", ""),
    )
    thread = AssistantThread.objects.create(company=tenant.company, created_by=tenant.owner)
    return AssistantMessage.objects.create(
        thread=thread, role="assistant", content="draft",
        proposed_action={"type": "send_reminder", "text": "Please pay", "customer_id": cust.id, **proposal},
    )


@pytest.mark.django_db
def test_a_second_confirm_does_not_send_again(tenant_a):
    from core.models import Notification

    msg = _reminder(tenant_a)
    first = confirm_proposed_action(tenant_a.company, tenant_a.owner, msg.id)
    assert first["status"] in ("sent", "queued")
    with pytest.raises(BusinessRuleError, match="No pending"):
        confirm_proposed_action(tenant_a.company, tenant_a.owner, msg.id)
    assert Notification.objects.filter(company=tenant_a.company, recipient="pay@ex.com").count() == 1
    assert AuditEvent.objects.filter(company=tenant_a.company, action="assistant.reminder.confirmed").count() == 1


@pytest.mark.django_db
def test_a_failed_email_is_reported_and_the_proposal_is_kept(tenant_a):
    msg = _reminder(tenant_a)
    failed = SimpleNamespace(id=1, status="FAILED", error="SMTP is not configured", share_link="")
    with patch("core.services.notifications.NotificationService.send", return_value=failed):
        with pytest.raises(BusinessRuleError, match="could not be sent"):
            confirm_proposed_action(tenant_a.company, tenant_a.owner, msg.id)
    msg.refresh_from_db()
    assert msg.proposed_action is not None  # the user can try again


@pytest.mark.django_db
@pytest.mark.parametrize(
    "notif_status,share_link,expect_status,expect_share",
    [
        ("SENT", "wamid.ABC", "sent", False),
        ("LINK_READY", "https://wa.me/919999999999?text=x", "link_ready", True),
        ("FAILED", "https://wa.me/919999999999?text=x", "failed", True),
    ],
)
def test_whatsapp_confirm_reports_each_outcome(tenant_a, notif_status, share_link, expect_status, expect_share):
    msg = _reminder(tenant_a, email="", phone="9999999999")
    Customer.objects.filter(name="Pay Me").update(email="")
    fake = SimpleNamespace(id=7, status=notif_status, error="", share_link=share_link)
    with patch("core.services.notifications.NotificationService.send", return_value=fake):
        result = confirm_proposed_action(tenant_a.company, tenant_a.owner, msg.id)
    assert result["status"] == expect_status
    assert result["requires_user_share"] is expect_share
    assert bool(result["share_link"]) is expect_share


@pytest.mark.django_db
def test_whatsapp_failure_still_offers_a_chat_link_and_says_it_failed(tenant_a):
    msg = _reminder(tenant_a, email="", phone="9999999999")
    Customer.objects.filter(name="Pay Me").update(email="")
    fake = SimpleNamespace(id=7, status="FAILED", error="HTTP 500", share_link="")
    with patch("core.services.notifications.NotificationService.send", return_value=fake):
        result = confirm_proposed_action(tenant_a.company, tenant_a.owner, msg.id)
    assert result["status"] == "failed"
    assert result["sent"] is False
    assert result["share_link"].startswith("https://wa.me/919999999999") or result["share_link"].startswith("https://wa.me/9999999999")
    assert result["error"] == "HTTP 500"


# --------------------------------------------------------------------------- assistant: answers (INP-08..10)

def test_routing_matches_word_starts_not_substrings():
    assert _pick_tools("However, the power is lower") == []
    assert _pick_tools("managing packaging") == []
    assert _pick_tools("who owes me money") == ["get_customer_outstanding"]
    assert "get_receivables_aging" in _pick_tools("show receivables aging")


def test_tax_guard_no_longer_blocks_ordinary_questions():
    assert not _looks_like_tax_question("यह काम कर दो")
    assert not _looks_like_tax_question("who was sold to Rahul last week")
    assert not _looks_like_tax_question("what percent of my sales went to Mumbai")
    assert _looks_like_tax_question("What is my GSTR liability?")
    assert _looks_like_tax_question("जीएसटी दर क्या है")


@pytest.mark.django_db
def test_unmatched_question_gets_help_not_a_data_dump(tenant_a):
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "hello there")
    assert "Try one of these" in msg.content
    assert "{" not in msg.content and "**" not in msg.content
    assert msg.tool_name == "basic"


@pytest.mark.django_db
def test_basic_answers_are_readable_text(tenant_a):
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "show receivables aging")
    assert "Receivables by age" in msg.content
    assert "get_receivables_aging" not in msg.content and '{"' not in msg.content


@pytest.mark.django_db
def test_two_matching_customers_produce_choices_not_a_draft(tenant_a):
    a = Customer.objects.create(company=tenant_a.company, name="Sharma Traders", state="Karnataka")
    b = Customer.objects.create(company=tenant_a.company, name="Sharma Sons", state="Karnataka")
    ex = ToolExecutor(tenant_a.company)
    res = ex.run("draft_payment_reminder", {"customer_name": "Sharma"})
    assert res["needs_clarification"] is True and "proposed_action" not in res
    assert {c["customer_id"] for c in res["candidates"]} == {a.id, b.id}


@pytest.mark.django_db
def test_a_typed_or_clicked_follow_up_keeps_the_original_action(tenant_a):
    a = Customer.objects.create(company=tenant_a.company, name="Sharma Traders", state="Karnataka")
    Customer.objects.create(company=tenant_a.company, name="Sharma Sons", state="Karnataka")
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    asked = AssistantMessage.objects.create(
        thread=thread, role="assistant", content="which?",
        proposed_action={
            "type": "clarify", "action": "draft_payment_reminder",
            "candidates": [{"customer_id": a.id, "customer_name": "Sharma Traders"}],
        },
    )
    typed = run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "Sharma Traders")
    assert typed.proposed_action["type"] == "send_reminder"
    assert typed.proposed_action["customer_id"] == a.id
    # The clicked chip sends the id explicitly.
    asked.proposed_action = None
    asked.save()
    clicked = run_assistant_turn(
        tenant_a.company, tenant_a.owner, thread, "Sharma Traders",
        hint={"action": "draft_payment_reminder", "customer_id": a.id},
    )
    assert clicked.proposed_action["customer_id"] == a.id


# --------------------------------------------------------------------------- assistant: model failures (INP-09)

@pytest.mark.django_db
def test_provider_failure_falls_back_with_a_notice_and_no_budget_charge(tenant_a):
    from insights.models import AiUsageLedger

    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    with patch("core.services.llm.llm_api_key_configured", return_value=True), patch(
        "core.services.llm.chat_with_tools", side_effect=RuntimeError("provider down")
    ):
        msg = run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "show receivables aging")
    assert msg.content.startswith("The AI service is unavailable")
    assert msg.tool_name == "basic"
    assert AiUsageLedger.objects.filter(company=tenant_a.company).count() == 0


@pytest.mark.django_db
def test_tokens_spent_before_a_failure_are_still_recorded(tenant_a):
    from insights.models import AiUsageLedger

    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    calls = {"n": 0}

    def fake_chat(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": "", "usage": {"tokens_in": 40, "tokens_out": 10}, "model": "m",
                "tool_calls": [{"name": "list_business_alerts", "arguments": {}}],
            }
        raise RuntimeError("second call failed")

    with patch("core.services.llm.llm_api_key_configured", return_value=True), patch(
        "core.services.llm.chat_with_tools", side_effect=fake_chat
    ):
        run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "any alerts?")
    row = AiUsageLedger.objects.get(company=tenant_a.company)
    assert (row.tokens_in, row.tokens_out) == (40, 10)


@pytest.mark.django_db
def test_a_turn_that_raises_leaves_no_orphan_user_message(tenant_a):
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    with patch("insights.assistant._run_rules_fallback", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            run_assistant_turn(tenant_a.company, tenant_a.owner, thread, "show receivables aging")
    assert thread.messages.count() == 0


@pytest.mark.django_db
def test_first_message_titles_the_chat(tenant_a):
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner, title="Chat")
    resp = tenant_a.client.post(
        f"/api/v1/insights/assistant/threads/{thread.id}/messages/", {"content": "show receivables aging"}, format="json",
    )
    assert resp.status_code == 201
    thread.refresh_from_db()
    assert thread.title == "show receivables aging"


@pytest.mark.django_db
def test_upsert_alerts_still_resolves_and_reopens(tenant_a):
    # Smoke: the locked, de-duplicating upsert keeps working end to end.
    upsert_alerts(tenant_a.company)
    upsert_alerts(tenant_a.company)
    live = BusinessAlertEvent.objects.filter(
        company=tenant_a.company, status__in=["OPEN", "SNOOZED"],
    ).values_list("code", "subject_key")
    assert len(list(live)) == len(set(live))


# --------------------------------------------------------------------------- AI consent switch (D12)

@pytest.mark.django_db
def test_owner_can_switch_ai_consent_and_it_is_audited(tenant_a):
    resp = tenant_a.client.post("/api/v1/insights/ai-consent/", {"enabled": False}, format="json")
    assert resp.status_code == 200 and resp.data == {"enabled": False}
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.ai_features_enabled is False
    event = AuditEvent.objects.get(company=tenant_a.company, action="company.ai_consent.disabled")
    assert event.metadata["before"] is True and event.metadata["after"] is False
    # Off means the Insights endpoints refuse, even for the owner.
    assert tenant_a.client.get("/api/v1/insights/alerts/").status_code == 403
    on = tenant_a.client.post("/api/v1/insights/ai-consent/", {"enabled": True}, format="json")
    assert on.status_code == 200
    assert AuditEvent.objects.filter(company=tenant_a.company, action="company.ai_consent.enabled").exists()


@pytest.mark.django_db
def test_setting_the_same_consent_writes_no_audit_row(tenant_a):
    tenant_a.client.post("/api/v1/insights/ai-consent/", {"enabled": True}, format="json")
    assert not AuditEvent.objects.filter(company=tenant_a.company, action__startswith="company.ai_consent").exists()


@pytest.mark.django_db
def test_non_owner_cannot_change_ai_consent_and_junk_is_400(tenant_a):
    assert tenant_a.staff_client.post("/api/v1/insights/ai-consent/", {"enabled": False}, format="json").status_code == 403
    assert tenant_a.client.post("/api/v1/insights/ai-consent/", {"enabled": "maybe"}, format="json").status_code == 400
    assert tenant_a.client.post("/api/v1/insights/ai-consent/", {}, format="json").status_code == 400
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.ai_features_enabled is True  # junk input never switches it off
