"""Persona journeys — the archetype × role matrix (see tests/personas/README.md).

Each journey: seed_archetype -> drive that persona's client -> assert the
capability boundary + the invariant sweep stays clean.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db

_TODO = "persona journey not yet implemented — see docstring / README"


def _stock_in(ns, product, qty="50", cost="60"):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=ns.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal(cost), user=ns.owner,
    )


def _plain_products(ns, n=3):
    return [p for p in ns.products if not p.track_batch][:n]


def test_pj_trader_sales_staff_boundary(boundary):
    """SALES_STAFF at a trader: quote + invoice + receipt for a GSTIN customer;
    denied cancel, manual journals, imports, adjustments, financial reports."""
    ns = seed_archetype("trader")
    plain = _plain_products(ns)
    for p in plain:
        _stock_in(ns, p)
    sc, oc = ns.sales_client, ns.owner_client
    p, cust = plain[0], ns.customers[0]

    # --- allowed: the sales job ---
    boundary.allowed(sc, "get", f"/api/v1/products/?search={p.sku}")
    inv = sc.post(
        "/api/v1/sales/invoices/",
        {"customer": cust.id, "invoice_type": "GST",
         "items": [{"product": p.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    iid = inv.data["id"]
    assert sc.post(f"/api/v1/sales/invoices/{iid}/complete/").status_code == 200
    rc = sc.post(
        "/api/v1/payments/receipts/",
        {"customer": cust.id, "amount": "100.00", "method": "CASH"}, format="json",
    )
    assert rc.status_code in (200, 201), rc.data

    # --- denied: everything outside it ---
    boundary.denied(sc, "post", f"/api/v1/sales/invoices/{iid}/cancel/", data={"reason": "x"}, format="json")
    boundary.denied(sc, "post", "/api/v1/accounting/journals/",
                    data={"entry_date": "2026-06-01", "narration": "x", "lines": []}, format="json")
    boundary.denied(sc, "post", "/api/v1/inventory/adjustments/",
                    data={"product": p.id, "quantity": "-1", "reason": "x"}, format="json")
    boundary.denied(sc, "get", "/api/v1/accounting/trial-balance/")
    boundary.denied(sc, "get", "/api/v1/accounting/profit-and-loss/")

    assert_all_invariants(ns.company)


def test_pj_trader_accountant_day(boundary):
    """ACCOUNTANT: post a manual JV (balanced), read P&L / trial balance / ageing;
    denied create-sales and manage-inventory. Books stay balanced."""
    ns = seed_archetype("trader")
    ac, oc = ns.acct_client, ns.owner_client
    p, cust = ns.products[0], ns.customers[0]

    from accounting.models import Account, JournalEntry

    cash = Account.objects.get(company=ns.company, code="1100").id
    opening_eq = Account.objects.get(company=ns.company, code="3200").id

    jv = ac.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-01", "narration": "capital introduced", "lines": [
            {"account": cash, "debit": "50000.00", "credit": "0"},
            {"account": opening_eq, "debit": "0", "credit": "50000.00"},
        ]},
        format="json",
    )
    assert jv.status_code == 201, jv.data
    assert ac.post(f"/api/v1/accounting/journals/{jv.data['id']}/post/").status_code in (200, 202)

    boundary.allowed(ac, "get", "/api/v1/accounting/trial-balance/")
    boundary.allowed(ac, "get", "/api/v1/accounting/profit-and-loss/")
    boundary.allowed(ac, "get", "/api/v1/accounting/balance-sheet/")

    # not the accountant's job
    boundary.denied(ac, "post", "/api/v1/sales/invoices/",
                    data={"customer": cust.id, "invoice_type": "GST",
                          "items": [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}]},
                    format="json")
    boundary.denied(ac, "post", "/api/v1/inventory/adjustments/",
                    data={"product": p.id, "quantity": "-1", "reason": "x"}, format="json")

    for e in JournalEntry.objects.filter(company=ns.company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_all_invariants(ns.company)


def test_pj_trader_viewer_readonly(boundary):
    """VIEWER in the current build is a UI-only role: BB-000422 denies masters
    browsing, BUG-319 denies financial reports, and the transactional lists +
    every mutation are denied too. This pins that "deny-all API surface"
    contract so a future capability regression is caught."""
    ns = seed_archetype("trader")
    vc = ns.viewer_client
    p, cust = ns.products[0], ns.customers[0]

    # masters — BB-000422
    boundary.denied(vc, "get", "/api/v1/products/")
    boundary.denied(vc, "get", "/api/v1/customers/")
    # transactional lists
    boundary.denied(vc, "get", "/api/v1/sales/invoices/")
    boundary.denied(vc, "get", "/api/v1/dashboard/")
    # financial reports — BUG-319
    boundary.denied(vc, "get", "/api/v1/accounting/trial-balance/")
    boundary.denied(vc, "get", "/api/v1/accounting/profit-and-loss/")
    # mutations
    boundary.denied(vc, "post", "/api/v1/sales/invoices/",
                    data={"customer": cust.id, "invoice_type": "GST",
                          "items": [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}]},
                    format="json")
    boundary.denied(vc, "post", "/api/v1/customers/", data={"name": "New Co", "state": "Karnataka"}, format="json")

    assert_all_invariants(ns.company)


def test_pj_trader_import_operator(boundary):
    """A SALES_STAFF + can_import user: bulk-import customers and products (with
    opening stock); re-running the identical product file creates nothing twice
    (SKU uniqueness rejects every row); denied every non-import mutation."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from inventory.models import StockBalance
    from masters.models import Product

    ns = seed_archetype("trader")
    ic = ns.importer_client

    def _upload(kind, content):
        return ic.post(
            "/api/v1/imports/",
            {"kind": kind, "file": SimpleUploadedFile("d.csv", content, content_type="text/csv")},
            format="multipart",
        )

    cust_csv = (
        b"name,phone,gstin,state\n"
        b"Imp Cust A,9810000001,,Karnataka\n"
        b"Imp Cust B,9810000002,,Karnataka\n"
    )
    jc = _upload("customers", cust_csv)
    assert jc.status_code == 201, jc.data
    assert jc.data["valid_rows"] == 2 and jc.data["error_rows"] == 0
    assert ic.post(f"/api/v1/imports/{jc.data['id']}/commit/").data["created"] == 2

    prod_csv = (
        b"name,sku,gst_rate,selling_price,opening_stock,unit_cost\n"
        b"Imp Widget,IMPP-1,18,120,40,70\n"
        b"Imp Gadget,IMPP-2,12,90,25,55\n"
    )
    jp = _upload("products", prod_csv)
    assert jp.status_code == 201 and jp.data["valid_rows"] == 2, jp.data
    cp = ic.post(f"/api/v1/imports/{jp.data['id']}/commit/")
    assert cp.status_code == 200 and cp.data["created"] == 2, cp.data
    assert StockBalance.objects.get(
        company=ns.company, product__sku="IMPP-1"
    ).on_hand == Decimal("40")
    n_prod = Product.objects.filter(company=ns.company).count()

    # replay the identical product file — SKU uniqueness rejects every row
    jp2 = _upload("products", prod_csv)
    if jp2.status_code == 201:
        assert jp2.data["valid_rows"] == 0
        assert ic.post(f"/api/v1/imports/{jp2.data['id']}/commit/").status_code == 400
    else:
        assert jp2.status_code == 400
    assert Product.objects.filter(company=ns.company).count() == n_prod

    # denied: anything that isn't running an import
    boundary.denied(ic, "post", "/api/v1/accounting/journals/",
                    data={"entry_date": "2026-06-01", "narration": "x", "lines": []}, format="json")
    boundary.denied(ic, "post", "/api/v1/inventory/adjustments/",
                    data={"product": Product.objects.filter(company=ns.company).first().id,
                          "quantity": "-1", "reason": "x"}, format="json")
    boundary.denied(ic, "get", "/api/v1/accounting/trial-balance/")

    assert_all_invariants(ns.company)


def test_pj_wholesale_owner_multi_godown_day():
    """WHOLESALE owner: receive stock into 3 godowns, transfer between two
    (TRANSFER_OUT + TRANSFER_IN net zero, company total unchanged), sell from a
    branch, close the month. Invariant sweep clean."""
    from inventory.models import MovementType, StockMovement
    from inventory.services import InventoryService

    ns = seed_archetype("wholesale")
    oc = ns.owner_client
    assert len(ns.warehouses) == 3
    wh_main, wh_n, wh_s = ns.warehouses
    plain = [p for p in ns.products if not p.track_batch][:3]
    p0 = plain[0]

    for wh in ns.warehouses:
        for p in plain:
            InventoryService.post_movement(
                company=ns.company, product=p, movement_type=MovementType.OPENING_STOCK,
                quantity=Decimal("30"), unit_cost=Decimal("60"), user=ns.owner, warehouse=wh,
            )
    assert InventoryService.available_quantity(ns.company, p0) == Decimal("90.000")

    tr = oc.post(
        "/api/v1/inventory/transfers/",
        {"from_warehouse": wh_n.id, "to_warehouse": wh_s.id, "notes": "rebalance",
         "lines": [{"product": p0.id, "quantity": "10.000"}]},
        format="json",
    )
    assert tr.status_code == 201, tr.data
    assert oc.post(f"/api/v1/inventory/transfers/{tr.data['id']}/complete/").status_code == 200
    out_m = StockMovement.objects.get(
        company=ns.company, reference_type="stock_transfer",
        reference_id=str(tr.data["id"]), movement_type=MovementType.TRANSFER_OUT)
    in_m = StockMovement.objects.get(
        company=ns.company, reference_type="stock_transfer",
        reference_id=str(tr.data["id"]), movement_type=MovementType.TRANSFER_IN)
    assert out_m.quantity + in_m.quantity == Decimal("0.000")
    assert InventoryService.available_quantity(ns.company, p0, warehouse=wh_s) == Decimal("40.000")
    assert InventoryService.available_quantity(ns.company, p0) == Decimal("90.000")

    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": ns.customers[0].id, "invoice_type": "GST",
         "items": [{"product": p0.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    assert oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/").status_code == 200

    per = oc.post(
        "/api/v1/accounting/periods/",
        {"name": "Apr 2026", "start_date": "2026-04-01", "end_date": "2026-04-30"},
        format="json",
    )
    assert per.status_code == 201, per.data
    assert oc.post(f"/api/v1/accounting/periods/{per.data['id']}/close/").status_code == 200

    assert_all_invariants(ns.company)


def test_pj_wholesale_accountant_period_close(boundary):
    """WHOLESALE accountant: post a balanced JV, review TB / balance sheet; period
    CLOSE is Owner-only (denied for ACCT); after the owner closes April, the
    accountant's back-dated posting into it is rejected."""
    from accounting.models import Account, JournalEntry

    ns = seed_archetype("wholesale")
    ac, oc = ns.acct_client, ns.owner_client
    cash = Account.objects.get(company=ns.company, code="1100").id
    oe = Account.objects.get(company=ns.company, code="3200").id

    jv = ac.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-05", "narration": "capital introduced", "lines": [
            {"account": cash, "debit": "20000.00", "credit": "0"},
            {"account": oe, "debit": "0", "credit": "20000.00"},
        ]},
        format="json",
    )
    assert jv.status_code == 201, jv.data
    assert ac.post(f"/api/v1/accounting/journals/{jv.data['id']}/post/").status_code in (200, 202)

    boundary.allowed(ac, "get", "/api/v1/accounting/trial-balance/")
    boundary.allowed(ac, "get", "/api/v1/accounting/balance-sheet/")

    per = oc.post(
        "/api/v1/accounting/periods/",
        {"name": "Apr 2026", "start_date": "2026-04-01", "end_date": "2026-04-30"},
        format="json",
    )
    assert per.status_code == 201, per.data
    pid = per.data["id"]
    boundary.denied(ac, "post", f"/api/v1/accounting/periods/{pid}/close/")
    assert oc.post(f"/api/v1/accounting/periods/{pid}/close/").status_code == 200

    late = ac.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-20", "narration": "back-dated", "lines": [
            {"account": cash, "debit": "100.00", "credit": "0"},
            {"account": oe, "debit": "0", "credit": "100.00"},
        ]},
        format="json",
    )
    if late.status_code == 201:
        posted = ac.post(f"/api/v1/accounting/journals/{late.data['id']}/post/")
        assert posted.status_code >= 400, posted.data
    else:
        assert late.status_code >= 400, late.data

    for e in JournalEntry.objects.filter(company=ns.company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_all_invariants(ns.company)


def test_pj_service_owner_no_stock():
    """SERVICE owner: raise GST invoices for non-stock items -> no StockMovement
    is ever created; a receipt allocates against the invoice normally; the
    invariant sweep stays clean."""
    from inventory.models import StockMovement

    ns = seed_archetype("service")
    oc = ns.owner_client
    svc, cust = ns.products[0], ns.customers[0]
    assert svc.track_inventory is False

    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": cust.id, "invoice_type": "GST",
         "items": [{"product": svc.id, "quantity": "2", "unit_price": "1500.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    iid = inv.data["id"]
    done = oc.post(f"/api/v1/sales/invoices/{iid}/complete/")
    assert done.status_code == 200, done.data
    grand = done.data["grand_total"]

    assert not StockMovement.objects.filter(company=ns.company).exists()

    rc = oc.post(
        "/api/v1/payments/receipts/",
        {"customer": cust.id, "amount": grand, "method": "UPI"}, format="json",
    )
    assert rc.status_code in (200, 201), rc.data
    alloc = oc.post(
        "/api/v1/payments/allocations/",
        {"receipt": rc.data["id"], "sales_invoice": iid, "amount": grand}, format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data

    assert not StockMovement.objects.filter(company=ns.company).exists()
    assert_all_invariants(ns.company)


def test_pj_newuser_register_to_first_invoice():
    """Register -> the registrant is OWNER -> dashboard loads -> create the first
    item + customer -> first invoice -> receipt. Invariant sweep clean."""
    from rest_framework.test import APIClient

    from accounts.models import Company, CompanyUser, User
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from masters.models import Customer, Product

    client = APIClient()
    reg = client.post(
        "/api/v1/auth/register/",
        {"company_name": "Brand New Shop", "email": "newbie@brandnew.test",
         "password": "StrongPass123!", "full_name": "New Bie", "phone": "9997776660",
         "state": "Karnataka", "registration_type": "REGULAR",
         "gstin": "29AAAAA0000A1ZY"},
        format="json",
    )
    assert reg.status_code in (200, 201), reg.data

    user = User.objects.get(email__iexact="newbie@brandnew.test")
    company = Company.objects.get(name="Brand New Shop")
    assert CompanyUser.objects.get(user=user, company=company).role == CompanyUser.Role.OWNER

    oc = APIClient()
    oc.force_authenticate(user=user)
    assert oc.get("/api/v1/dashboard/").status_code == 200

    prod = Product.objects.create(
        company=company, name="First Item", sku="FIRST-1", gst_rate=Decimal("18"),
        purchase_price=Decimal("50"), selling_price=Decimal("100"),
    )
    InventoryService.post_movement(
        company=company, product=prod, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"), unit_cost=Decimal("50"), user=user,
    )
    cust = Customer.objects.create(company=company, name="First Customer", state="Karnataka")

    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": cust.id, "invoice_type": "GST",
         "items": [{"product": prod.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    done = oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")
    assert done.status_code == 200, done.data

    rc = oc.post(
        "/api/v1/payments/receipts/",
        {"customer": cust.id, "amount": done.data["grand_total"], "method": "CASH"},
        format="json",
    )
    assert rc.status_code in (200, 201), rc.data

    assert_all_invariants(company)


def test_pj_migration_wholesale_large_cutover_with_history():
    """As PJ-MIGRATION-TRADER but multi-godown opening stock and more parties: AR
    split across 3 debtors, AP across 2 creditors, opening stock across 3 godowns.
    opening_ties_out holds; the redo path (post -> reverse) leaves it holding;
    the first live invoice continues the old numbering series."""
    from accounting.models import Account, JournalEntry
    from accounting.reports import trial_balance
    from core.invariants.reports import opening_ties_out
    from inventory.models import MovementType, Warehouse
    from inventory.services import InventoryService
    from masters.models import Customer, Product, Supplier

    ns = seed_archetype("migration")
    company, oc = ns.company, ns.owner_client
    CUTOVER = "2026-04-01"

    whs = [InventoryService.default_warehouse(company)]
    for name, code in (("North", "NR"), ("South", "SR")):
        r = oc.post("/api/v1/inventory/warehouses/", {"name": name, "code": code}, format="json")
        assert r.status_code == 201, r.data
        whs.append(Warehouse.objects.get(company=company, code=code))

    nsr = oc.patch(
        "/api/v1/sales/invoices/number-series/",
        {"prefix": "WS", "next_number": 421, "padding": 6}, format="json",
    )
    assert nsr.status_code == 200, nsr.data

    items = [
        Product.objects.create(company=company, name=f"WItem {i}", sku=f"WMIG-{i:03d}",
                               gst_rate=Decimal("18"), purchase_price=Decimal("40"),
                               selling_price=Decimal("70"))
        for i in range(9)
    ]
    debtors = [
        Customer.objects.create(company=company, name=f"Debtor {i}", state="Karnataka",
                                gstin=f"29AAAAA{i:04d}A1Z5")
        for i in range(3)
    ]
    creditors = [
        Supplier.objects.create(company=company, name=f"Creditor {i}", state="Karnataka",
                                gstin=f"29ZZZZZ{i:04d}A1Z5")
        for i in range(2)
    ]

    # opening stock across 3 godowns: 9 items x 3 godowns x 20 @ 40 = 21,600
    for wh in whs:
        for it in items:
            InventoryService.post_movement(
                company=company, product=it, movement_type=MovementType.OPENING_STOCK,
                quantity=Decimal("20"), unit_cost=Decimal("40"), user=ns.owner, warehouse=wh,
            )

    def _a(code):
        return Account.objects.get(company=company, code=code).id

    oe = Account.objects.filter(company=company, code="3200").first() or Account.objects.create(
        company=company, code="3200", name="Opening Balance Equity", type="EQUITY"
    )
    lines = [
        {"account": _a("1100"), "debit": "10000.00", "credit": "0"},
        {"account": _a("1500"), "debit": "50000.00", "credit": "0"},
        {"account": _a("1400"), "debit": "21600.00", "credit": "0"},
    ]
    for d in debtors:
        lines.append({"account": _a("1200"), "debit": "5000.00", "credit": "0", "customer": d.id})
    for c in creditors:
        lines.append({"account": _a("2100"), "debit": "0", "credit": "7000.00", "supplier": c.id})
    # Dr 10000+50000+21600+15000 = 96600 ; Cr 14000 ; Opening Equity Cr = 82600
    lines.append({"account": oe.id, "debit": "0", "credit": "82600.00"})

    jr = oc.post(
        "/api/v1/accounting/journals/",
        {"entry_date": CUTOVER, "narration": "opening TB", "lines": lines}, format="json",
    )
    assert jr.status_code == 201, jr.data
    assert oc.post(f"/api/v1/accounting/journals/{jr.data['id']}/post/").status_code in (200, 202)

    assert not opening_ties_out(company), opening_ties_out(company)
    assert trial_balance(company)["balanced"]
    assert_all_invariants(company)

    # redo path — a wrong extra opening adjustment, posted then reversed
    bad = oc.post(
        "/api/v1/accounting/journals/",
        {"entry_date": CUTOVER, "narration": "oops", "lines": [
            {"account": _a("1100"), "debit": "999.00", "credit": "0"},
            {"account": oe.id, "debit": "0", "credit": "999.00"},
        ]},
        format="json",
    )
    assert bad.status_code == 201, bad.data
    bid = bad.data["id"]
    assert oc.post(f"/api/v1/accounting/journals/{bid}/post/").status_code in (200, 202)
    rev = oc.post(f"/api/v1/accounting/journals/{bid}/reverse/")
    assert rev.status_code in (200, 201, 202), rev.data
    assert JournalEntry.objects.get(pk=bid).status == JournalEntry.Status.REVERSED

    assert not opening_ties_out(company), opening_ties_out(company)
    assert trial_balance(company)["balanced"]

    fv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": debtors[0].id, "invoice_type": "GST",
         "items": [{"product": items[0].id, "quantity": "1", "unit_price": "70.00", "gst_rate": "18"}]},
        format="json",
    )
    assert fv.status_code == 201, fv.data
    fdone = oc.post(f"/api/v1/sales/invoices/{fv.data['id']}/complete/")
    assert fdone.status_code == 200, fdone.data
    assert fdone.data["number"].endswith("000421"), fdone.data["number"]

    assert_all_invariants(company)


def test_pj_wholesale_godown_custodian():
    """PJ-WHOLE-GODOWN (QOS-0008) — the P4 stock custodian: a SALES_STAFF member
    with `can_manage_inventory` explicitly granted. Does inward + inter-godown
    transfer; is denied financial reports, journal posting, and export. The day
    leaves the ledger / stock consistent."""
    from decimal import Decimal

    from inventory.models import MovementType, StockMovement
    from inventory.services import InventoryService

    ns = seed_archetype("wholesale")
    gc = ns.godown_client
    wh_main, wh_n, wh_s = ns.warehouses
    p0 = next(p for p in ns.products if not p.track_batch)

    # --- in role: inward stock into every godown ---
    for wh in ns.warehouses:
        InventoryService.post_movement(
            company=ns.company, product=p0, movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("20"), unit_cost=Decimal("60"), user=ns.godown, warehouse=wh,
        )
    assert InventoryService.available_quantity(ns.company, p0) == Decimal("60.000")

    # --- in role: create + complete an inter-godown transfer ---
    tr = gc.post(
        "/api/v1/inventory/transfers/",
        {"from_warehouse": wh_n.id, "to_warehouse": wh_s.id, "notes": "rebalance",
         "lines": [{"product": p0.id, "quantity": "8.000"}]},
        format="json",
    )
    assert tr.status_code == 201, tr.data
    assert gc.post(f"/api/v1/inventory/transfers/{tr.data['id']}/complete/").status_code == 200
    out_m = StockMovement.objects.get(
        company=ns.company, reference_type="stock_transfer",
        reference_id=str(tr.data["id"]), movement_type=MovementType.TRANSFER_OUT)
    in_m = StockMovement.objects.get(
        company=ns.company, reference_type="stock_transfer",
        reference_id=str(tr.data["id"]), movement_type=MovementType.TRANSFER_IN)
    assert out_m.quantity + in_m.quantity == Decimal("0.000")
    assert InventoryService.available_quantity(ns.company, p0) == Decimal("60.000")

    # --- in role: read stock balances / warehouses ---
    assert gc.get("/api/v1/inventory/balances/").status_code == 200
    assert gc.get("/api/v1/inventory/warehouses/").status_code == 200

    # --- out of role: financial reports, journals, export are denied ---
    assert gc.get("/api/v1/reports/profit-and-loss/").status_code in (403, 404), \
        "custodian must not see the P&L"
    assert gc.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-05", "narration": "nope", "lines": []},
        format="json",
    ).status_code in (403, 404), "custodian must not post journals"
    assert gc.get("/api/v1/reports/trial-balance/export/").status_code in (403, 404, 405)

    assert_all_invariants(ns.company)
