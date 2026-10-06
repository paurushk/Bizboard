"""FMEA wave 3–5 tests. Names are test_fmea2_ and do not reuse test_tc_fmea_."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from accounting.services import seed_chart_of_accounts
from contracts.models import Contract
from contracts.tasks import refresh_contract_statuses
from reporting.gst_periods import soft_close_period
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_fmea2_011_skipped_month_keeps_error(tenant_a):
    from accounting.models import FixedAsset, JournalEntry
    from accounting.services import BooksHealthService, PostingService
    from accounting.tasks import _depreciate_company_assets

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    asset = FixedAsset.objects.create(
        company=tenant_a.company,
        name="Press",
        asset_account=PostingService._account(tenant_a.company, "1600"),
        accumulated_depreciation_account=PostingService._account(tenant_a.company, "1650"),
        depreciation_expense_account=PostingService._account(tenant_a.company, "5300"),
        acquisition_date="2026-07-01",
        acquisition_cost=Decimal("12000.00"),
        useful_life_months=36,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    soft_close_period(tenant_a.company, "2026-07", tenant_a.owner)
    _depreciate_company_assets(tenant_a.company.id)
    asset.refresh_from_db()
    assert "2026-07" in asset.last_depreciation_error
    assert not JournalEntry.objects.filter(
        company=tenant_a.company, source_id=asset.id, purpose="DEPRECIATION-2026-07",
    ).exists()
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_id=asset.id, purpose="DEPRECIATION-2026-08",
        status=JournalEntry.Status.POSTED,
    ).exists()
    alerts = BooksHealthService.control_balances(tenant_a.company)["alerts"]
    assert any(alert["code"] == "DEPRECIATION_FAILED" for alert in alerts)


def test_fmea2_013_contract_job_skips_flag_off(tenant_a, tenant_b):
    today = timezone.localdate()
    tenant_a.company.feature_flags = {"ENABLE_CONTRACTS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    tenant_b.company.feature_flags = {"ENABLE_CONTRACTS": False}
    tenant_b.company.save(update_fields=["feature_flags"])
    customer_a = make_customer(tenant_a.company)
    customer_b = make_customer(tenant_b.company)
    contract_a = Contract.objects.create(
        company=tenant_a.company, customer=customer_a, contract_type=Contract.Type.AMC,
        start_date=today - timedelta(days=40), end_date=today - timedelta(days=1),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    Contract.objects.filter(pk=contract_a.pk).update(status=Contract.Status.ACTIVE)
    contract_b = Contract.objects.create(
        company=tenant_b.company, customer=customer_b, contract_type=Contract.Type.AMC,
        start_date=today - timedelta(days=40), end_date=today - timedelta(days=1),
        created_by=tenant_b.owner, updated_by=tenant_b.owner,
    )
    Contract.objects.filter(pk=contract_b.pk).update(status=Contract.Status.ACTIVE)
    result = refresh_contract_statuses()
    contract_a.refresh_from_db()
    contract_b.refresh_from_db()
    assert contract_a.status == Contract.Status.EXPIRED
    assert contract_b.status == Contract.Status.ACTIVE
    assert result["skipped_flag_off"] >= 1


def test_fmea2_014_gstn_needs_env_and_flag(tenant_a, tenant_b):
    tenant_a.company.feature_flags = {"ENABLE_GSTN_JSON": True, "ENABLE_GSTR": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    tenant_b.company.feature_flags = {"ENABLE_GSTN_JSON": False, "ENABLE_GSTR": True}
    tenant_b.company.save(update_fields=["feature_flags"])
    url = "/api/v1/reports/gstr1/?period=2026-08&format=gstn-json"
    with override_settings(ENABLE_GSTN_JSON=False, ENABLE_GSTR=True):
        refused = tenant_a.client.get(url)
        assert refused.status_code == 400
    with override_settings(ENABLE_GSTN_JSON=True, ENABLE_GSTR=True):
        other = tenant_b.client.get(url)
        assert other.status_code == 400
        ok = tenant_a.client.get(url)
        assert ok.status_code == 200, ok.data
        assert "not a GSTN portal upload" in str(ok.data.get("disclaimer") or ok.data)
    from core.services.feature_flags import flag_enabled

    tenant_a.company.refresh_from_db()
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        del tenant_a.company._feature_flags_cache
    with override_settings(ENABLE_GSTN_JSON=False):
        assert flag_enabled(tenant_a.company, "ENABLE_GSTN_JSON") is False
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        del tenant_a.company._feature_flags_cache
    with override_settings(ENABLE_GSTN_JSON=True):
        assert flag_enabled(tenant_a.company, "ENABLE_GSTN_JSON") is True


def test_fmea2_015_shopify_holds_large_delta(tenant_a, tenant_b):
    import base64
    import hashlib
    import hmac

    from core.services.gsp_secrets import encrypt_gsp_credentials
    from integrations.models import IntegrationConnection
    from inventory.models import MovementType, StockBalance, StockMovement
    from inventory.services import InventoryService
    from core.invariants.inventory import balance_equals_movements
    from integrations.shopify import ShopifyWebhookView
    from rest_framework.test import APIRequestFactory
    from sales.models import SalesInvoice
    from sales.services import SalesService
    from tests.conftest import create_draft_invoice

    product = make_product(tenant_a.company, sku="SHOP-1", gst_rate="0")
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    add_stock(tenant_a, product, "10")
    conn = IntegrationConnection.objects.create(
        company=tenant_a.company,
        provider=IntegrationConnection.Provider.SHOPIFY,
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={"shop_domain": "hold.myshopify.com", "warehouse_id": warehouse.id},
    )
    IntegrationConnection.objects.create(
        company=tenant_b.company,
        provider=IntegrationConnection.Provider.SHOPIFY,
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={"shop_domain": "other.myshopify.com", "warehouse_id": InventoryService.default_warehouse(tenant_b.company).id},
    )

    def _post(payload, delivery):
        body = json.dumps(payload).encode()
        digest = base64.b64encode(hmac.new(b"sekret", body, hashlib.sha256).digest()).decode()
        request = APIRequestFactory().post(
            "/api/v1/integrations/shopify/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_SHOPIFY_SHOP_DOMAIN="hold.myshopify.com",
            HTTP_X_SHOPIFY_HMAC_SHA256=digest,
            HTTP_X_SHOPIFY_WEBHOOK_ID=delivery,
            HTTP_X_SHOPIFY_TOPIC="inventory_levels/update",
        )
        return ShopifyWebhookView.as_view()(request)

    first = _post(
        {"sku": "SHOP-1", "available": "10", "updated_at": "2026-10-01T00:00:00Z", "inventory_item_id": "11"},
        "d1",
    )
    assert first.status_code == 200, getattr(first, "data", first)
    assert StockMovement.objects.filter(
        company=tenant_a.company, movement_type=MovementType.ADJUSTMENT, reference_type="shopify",
    ).count() == 0
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    SalesService.complete(invoice, tenant_a.owner)
    before = StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=warehouse).on_hand
    assert before == Decimal("9")
    stale = _post(
        {"sku": "SHOP-1", "available": "10", "updated_at": "2026-09-01T00:00:00Z", "inventory_item_id": "11"},
        "d2",
    )
    assert stale.status_code == 200
    after = StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=warehouse).on_hand
    assert after == before
    zero = _post(
        {"sku": "SHOP-1", "available": str(after), "updated_at": "2026-10-02T00:00:00Z", "inventory_item_id": "11"},
        "d3",
    )
    assert zero.status_code == 200
    conn.refresh_from_db()
    assert "2026-10-02" in (conn.metadata.get("shopify_applied_at") or {}).get("11", "")
    held = _post(
        {"sku": "SHOP-1", "available": "0", "updated_at": "2026-10-03T00:00:00Z", "inventory_item_id": "11"},
        "d4",
    )
    assert held.status_code == 200
    conn.refresh_from_db()
    assert "11" in (conn.metadata.get("shopify_pending") or {})
    assert StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=warehouse).on_hand == after
    again = _post(
        {"sku": "SHOP-1", "available": "0", "updated_at": "2026-10-03T00:00:00Z", "inventory_item_id": "11"},
        "d4",
    )
    assert again.data.get("status") == "duplicate"
    assert StockMovement.objects.filter(company=tenant_b.company, movement_type=MovementType.ADJUSTMENT).count() == 0
    assert balance_equals_movements(tenant_a.company) == []


def test_fmea2_016_shopify_domain_unique(tenant_a, tenant_b):
    import base64
    import hashlib
    import hmac

    from core.services.gsp_secrets import encrypt_gsp_credentials
    from django.db import IntegrityError, transaction
    from django.test import RequestFactory
    from integrations.models import IntegrationConnection
    from integrations.shopify import ShopifyWebhookView
    from inventory.models import MovementType, StockMovement

    IntegrationConnection.objects.create(
        company=tenant_a.company, provider="SHOPIFY", shop_domain="clash.myshopify.com",
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={"shop_domain": "clash.myshopify.com"},
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            IntegrationConnection.objects.create(
                company=tenant_b.company, provider="SHOPIFY", shop_domain="clash.myshopify.com",
                encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
                metadata={"shop_domain": "clash.myshopify.com"},
            )
    left = IntegrationConnection.objects.get(company=tenant_a.company, provider="SHOPIFY")
    right = IntegrationConnection.objects.create(
        company=tenant_b.company, provider="SHOPIFY", shop_domain="",
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={},
    )
    IntegrationConnection.objects.filter(pk__in=[left.pk, right.pk]).update(
        shop_domain="", metadata={"shop_domain": "clash.myshopify.com"},
    )
    body = b"{}"
    digest = base64.b64encode(hmac.new(b"sekret", body, hashlib.sha256).digest()).decode()
    request = RequestFactory().post(
        "/api/v1/integrations/shopify/webhook/",
        data=body, content_type="application/json",
        HTTP_X_SHOPIFY_SHOP_DOMAIN="clash.myshopify.com",
        HTTP_X_SHOPIFY_HMAC_SHA256=digest,
        HTTP_X_SHOPIFY_TOPIC="inventory_levels/update",
    )
    response = ShopifyWebhookView.as_view()(request)
    assert response.status_code == 401
    assert StockMovement.objects.filter(movement_type=MovementType.ADJUSTMENT).count() == 0


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=True)
def test_fmea2_017_aa_live_fetch_closed(tenant_a):
    from banking.models import AaConsent, AaTransaction

    tenant_a.company.feature_flags = {"ENABLE_ACCOUNT_AGGREGATOR": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    live = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {"consent_id": "missing-consent", "use_live_fiu": True, "status": "ACTIVE"},
        format="json",
    )
    assert live.status_code == 400
    assert AaConsent.objects.filter(company=tenant_a.company).count() == 0
    assert AaTransaction.objects.filter(company=tenant_a.company).count() == 0
    AaConsent.objects.create(
        company=tenant_a.company, consent_id="held-1", status=AaConsent.Status.ACTIVE,
        fi_type="DEPOSIT", created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    stored = tenant_a.client.post(
        "/api/v1/banking/aa/ingest/",
        {
            "consent_id": "held-1",
            "status": "ACTIVE",
            "transactions": [{"txn_id": "typed-1", "amount": "10.00", "txn_date": "2026-10-01"}],
        },
        format="json",
    )
    assert stored.status_code == 201, stored.data
    row = AaTransaction.objects.get(company=tenant_a.company, txn_id="typed-1")
    assert row.raw.get("ingest_source") == "client"


def test_fmea2_017_company_fiu_credential_round_trip(tenant_a):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from banking.fiu_adapter import company_fiu_api_key

    with pytest.raises(CommandError, match="Pass --token"):
        call_command("set_company_fiu_credential", company_id=tenant_a.company.id, token="  ")
    call_command(
        "set_company_fiu_credential",
        company_id=tenant_a.company.id,
        token="tenant-token",
        stdout=StringIO(),
    )
    assert company_fiu_api_key(tenant_a.company) == "tenant-token"


def test_fmea2_existing_gaps_command_is_read_only():
    out = StringIO()
    call_command("fmea2_existing_gaps", stdout=out)
    text = out.getvalue()
    assert "SalesInvoice_completed_without_audit" in text
    assert "complaints_with_return_and_credit_note" in text
    assert "campaign_roi=computed_on_read" in text


def test_fmea2_existing_gaps_apply_backfills_and_clears_return_note(tenant_a):
    from complaints.models import Complaint
    from core.models import AuditEvent
    from sales.models import SalesCreditNote, SalesInvoice, SalesReturn

    customer = make_customer(tenant_a.company)
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, invoice_type="NON_GST",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    SalesInvoice.objects.filter(pk=invoice.pk).update(status=SalesInvoice.Status.COMPLETED)
    sales_return = SalesReturn.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=invoice,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    note = SalesCreditNote.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=invoice,
        sales_return=sales_return, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    complaint = Complaint.objects.create(
        company=tenant_a.company, customer=customer, category=Complaint.Category.DAMAGED,
        description="both", sales_return=sales_return, sales_credit_note=note,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    separate = SalesCreditNote.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=invoice,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    SalesCreditNote.objects.filter(pk=separate.pk).update(status=SalesCreditNote.Status.COMPLETED)
    separate_complaint = Complaint.objects.create(
        company=tenant_a.company, customer=customer, category=Complaint.Category.OTHER,
        description="separate", sales_return=sales_return, sales_credit_note=separate,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    call_command("fmea2_existing_gaps", apply=True, stdout=StringIO())
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk),
        description="backfill: completed document had no audit row",
    ).count() == 1
    complaint.refresh_from_db()
    note.refresh_from_db()
    assert complaint.sales_return_id == sales_return.pk
    assert complaint.sales_credit_note_id is None
    assert note.status == SalesCreditNote.Status.DRAFT
    separate.refresh_from_db()
    separate_complaint.refresh_from_db()
    assert separate.status == SalesCreditNote.Status.COMPLETED
    assert separate_complaint.sales_credit_note_id == separate.pk
    call_command("fmea2_existing_gaps", apply=True, stdout=StringIO())
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk),
        description="backfill: completed document had no audit row",
    ).count() == 1


def test_fmea2_shopify_repair_posts_only_with_on_hand(tenant_a):
    from django.core.management.base import CommandError

    from inventory.models import MovementType, StockBalance, StockMovement
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, sku="SHOP-FIX")
    add_stock(tenant_a, product, 10)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, product=product, warehouse=warehouse,
        movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-4"),
        reason="Shopify inventory_levels/update", reference_type="shopify", reference_id="11",
        user=tenant_a.owner,
    )
    with pytest.raises(CommandError, match="on-hand"):
        call_command(
            "repair_shopify_overwrites", company_id=tenant_a.company.id, apply=True, stdout=StringIO(),
        )
    balance = StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=warehouse)
    assert balance.on_hand == Decimal("6")
    call_command(
        "repair_shopify_overwrites",
        company_id=tenant_a.company.id,
        apply=True,
        product_id=product.id,
        warehouse_id=warehouse.id,
        on_hand="10",
        stdout=StringIO(),
    )
    balance.refresh_from_db()
    assert balance.on_hand == Decimal("10")
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type="shopify_repair",
    ).count() == 1
    other = make_product(tenant_a.company, sku="SHOP-NONE")
    add_stock(tenant_a, other, 3)
    with pytest.raises(CommandError, match="No Shopify adjustment"):
        call_command(
            "repair_shopify_overwrites",
            company_id=tenant_a.company.id,
            apply=True,
            product_id=other.id,
            warehouse_id=warehouse.id,
            on_hand="1",
            stdout=StringIO(),
        )


def test_fmea2_012_linked_draft_job_becomes_in_progress(tenant_a):
    from sales.models import SalesInvoice
    from workshop.models import JobCard
    from workshop.services import convert_to_invoice

    customer = make_customer(tenant_a.company)
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, invoice_type="NON_GST",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    job = JobCard.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=invoice,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    convert_to_invoice(job, tenant_a.owner)
    job.refresh_from_db()
    assert job.status == JobCard.Status.IN_PROGRESS
    assert job.sales_invoice_id == invoice.pk
