"""DAN-14: audit trail for attention actions, and the dedupe-key contract."""

import re
from pathlib import Path

import pytest
from django.core.cache import cache

from core.models import AuditEvent
from insights import attention as attention_module
from insights.attention import (
    _row,
    assign_attention_row,
    dismiss_attention_row,
    reopen_attention_row,
    snooze_attention_row,
)

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT.parent / "docs" / "ATTENTION_DEDUPE_KEYS.md"
SOURCES = [
    ROOT / "insights" / "alerts.py",
    ROOT / "insights" / "services.py",
    ROOT / "insights" / "attention.py",
    ROOT / "insights" / "customer_actions.py",
    ROOT / "payments" / "predictive_dunning.py",
]


def _owner(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# --- audit -----------------------------------------------------------------

@pytest.mark.django_db
def test_every_action_writes_an_audit_event_with_before_and_after(tenant_a, monkeypatch):
    monkeypatch.setattr(attention_module, "_live_row", lambda company, key: {"severity": "warning", "code": "DEAD_STOCK"})
    cu = _owner(tenant_a)
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ACTION_ASSIGNMENT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    key = "DEAD_STOCK:product:1"

    snooze_attention_row(tenant_a.company, cu, dedupe_key=key, days=3, reason="call supplier")
    assign_attention_row(tenant_a.company, cu, dedupe_key=key, assignee_id=cu.id)
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=key, reason="not selling")
    reopen_attention_row(tenant_a.company, cu, dedupe_key=key)

    events = {
        e.action: e for e in AuditEvent.objects.filter(company=tenant_a.company, entity_type="AttentionRow")
    }
    assert set(events) == {"attention.snoozed", "attention.assigned", "attention.dismissed", "attention.reopened"}
    snoozed = events["attention.snoozed"]
    assert snoozed.user_id == tenant_a.owner.pk
    assert snoozed.metadata["dedupe_key"] == key and snoozed.metadata["reason"] == "call supplier"
    assert snoozed.metadata["before"]["snooze_until"] is None and snoozed.metadata["after"]["snooze_until"]
    dismissed = events["attention.dismissed"]
    assert dismissed.metadata["before"]["dismissed"] is False and dismissed.metadata["after"]["dismissed"] is True
    reopened = events["attention.reopened"]
    assert reopened.metadata["before"]["dismissed"] is True and reopened.metadata["after"]["dismissed"] is False
    assert events["attention.assigned"].metadata["after"]["assigned_to"] == cu.id


@pytest.mark.django_db
def test_a_refused_action_leaves_no_audit_event(tenant_a):
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        dismiss_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="IRN_FAILED:sales_invoice:1")
    assert not AuditEvent.objects.filter(company=tenant_a.company, entity_type="AttentionRow").exists()


@pytest.mark.django_db
def test_a_long_key_is_audited_in_full_in_the_metadata(tenant_a):
    key = "DEAD_STOCK:" + "x" * 150
    dismiss_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key=key)
    event = AuditEvent.objects.get(company=tenant_a.company, action="attention.dismissed")
    assert event.metadata["dedupe_key"] == key and len(event.entity_id) <= 64


# --- key contract ------------------------------------------------------------

def _source_text():
    return {src.name: src.read_text(encoding="utf-8") for src in SOURCES}


def test_every_explicit_key_shape_is_documented():
    doc = DOC.read_text(encoding="utf-8")
    shapes = set()
    for text in _source_text().values():
        for match in re.finditer(r'dedupe(?:_key)?\s*=\s*f?"([^"\n]*)"', text):
            shapes.add(match.group(1))
    shapes = {s for s in shapes if ":" in s}
    assert len(shapes) >= 15, "key scan found too little: the pattern needs updating"
    undocumented = sorted(s for s in shapes if s not in doc)
    assert undocumented == [], f"add these key shapes to docs/ATTENTION_DEDUPE_KEYS.md: {undocumented}"


def test_every_emitted_code_is_documented_and_classified():
    doc = DOC.read_text(encoding="utf-8")
    codes = set()
    for text in _source_text().values():
        codes |= set(re.findall(r'code="([A-Z][A-Z_0-9]+)"', text))
        codes |= set(re.findall(r'_alert\(\s*"([A-Z][A-Z_0-9]+)"', text))
        codes |= set(re.findall(r'"code":\s*"([A-Z][A-Z_0-9]+)"', text))
    assert len(codes) >= 35
    missing = sorted(c for c in codes if c not in doc)
    assert missing == [], f"add these codes to docs/ATTENTION_DEDUPE_KEYS.md: {missing}"
    for code in attention_module.NON_DISMISSIBLE | attention_module.REASON_REQUIRED_CODES:
        assert code in doc
    # A code a detector can emit must be one the actions accept, or a person could not dismiss it.
    assert sorted(c for c in codes if c not in attention_module.KNOWN_CODES) == []
    # And the rule sets only name codes that exist.
    assert (attention_module.NON_DISMISSIBLE | attention_module.REASON_REQUIRED_CODES) <= attention_module.KNOWN_CODES


def test_default_key_shape():
    row = _row(
        code="X_CODE", severity="info", title="t", money_impact_paise=0, reason="r", action_label="a",
        action_href="/attention", source_ticket="T", entity_type="product", entity_id=5,
    )
    assert row["dedupe_key"] == "X_CODE:product:5"


# --- DAN-15: bulk detectors -------------------------------------------------

def _invoices(tenant, customer, count, *, status, days_overdue=40, total="100.00"):
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from sales.models import SalesInvoice

    due = timezone.localdate() - timedelta(days=days_overdue)
    SalesInvoice.objects.bulk_create([
        SalesInvoice(
            company=tenant.company, customer=customer, status=status,
            invoice_type=SalesInvoice.InvoiceType.NON_GST, invoice_date=due, due_date=due,
            taxable_total=Decimal(total), grand_total=Decimal(total),
        )
        for _ in range(count)
    ])


@pytest.mark.django_db
@pytest.mark.no_invariant_check  # bulk_create is a fixture, not a posted chain
def test_customers_whose_overdue_invoices_are_all_paid_do_not_crowd_out_one_who_owes(tenant_a, monkeypatch):
    from decimal import Decimal

    from django.utils import timezone

    from payments.models import CustomerReceipt  # noqa: F401  (documents what 'paid' means below)
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    paid_customers = [make_customer(tenant_a.company, name=f"Paid {i}") for i in range(35)]
    for customer in paid_customers:
        _invoices(tenant_a, customer, 1, status=SalesInvoice.Status.COMPLETED)
    # "Paid" here = the ledger says nothing is outstanding on these invoices.
    from ledgers.services import LedgerService

    real = LedgerService.bulk_sales_invoice_outstanding
    paid_ids = set(SalesInvoice.objects.filter(company=tenant_a.company).values_list("id", flat=True))
    debtor = make_customer(tenant_a.company, name="Still Owes")
    _invoices(tenant_a, debtor, 1, status=SalesInvoice.Status.COMPLETED, total="500.00")

    def fake(company, invoice_ids):
        out = real(company, invoice_ids)
        return {k: (Decimal("0") if k in paid_ids else v) for k, v in out.items()}

    monkeypatch.setattr(LedgerService, "bulk_sales_invoice_outstanding", staticmethod(fake))
    calls = []
    import payments.dunning as dunning

    original = dunning.customer_risk_snapshot
    monkeypatch.setattr(dunning, "customer_risk_snapshot", lambda company, cust, **kw: calls.append(cust.id) or original(company, cust, **kw))
    rows = attention_module._overdue_customer_rows(tenant_a.company, timezone.localdate())
    assert calls == [debtor.id], "only the customer who really owes gets the expensive snapshot"
    assert [r["entity_ref"]["id"] for r in rows] == [debtor.id]


@pytest.mark.django_db
@pytest.mark.no_invariant_check
def test_residual_return_rows_use_a_constant_number_of_queries(tenant_a):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company)
    _invoices(tenant_a, customer, 1, status=SalesInvoice.Status.RETURNED)
    with CaptureQueriesContext(connection) as one:
        attention_module._residual_return_rows(tenant_a.company)
    _invoices(tenant_a, customer, 15, status=SalesInvoice.Status.RETURNED)
    with CaptureQueriesContext(connection) as many:
        rows = attention_module._residual_return_rows(tenant_a.company)
    assert len(rows) == 16
    assert len(many.captured_queries) == len(one.captured_queries)
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 16


@pytest.mark.django_db
def test_dashboard_payload_carries_the_first_low_stock_rows(tenant_a):
    from reporting.services import ReportService

    data = ReportService.dashboard(tenant_a.company)
    assert data["low_stock_items"] == [] and data["low_stock_count"] == 0
    body = tenant_a.client.get("/api/v1/dashboard/")
    assert body.status_code == 200
    payload = body.data.get("data") or body.data
    assert "low_stock_items" in payload or "lowStockItems" in payload
