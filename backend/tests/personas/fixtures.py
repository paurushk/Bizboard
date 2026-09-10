"""Archetype fixtures for persona journeys (tests/personas/).

`seed_archetype(kind)` builds a company shaped like one kind of Indian small
business, with a user + force-authenticated APIClient for each role that
archetype has. Persona-journey tests drive these clients through a "normal day"
and assert the capability + visibility boundaries hold and the invariant sweep
stays clean.

Kinds:
  retail      — counter shop: 1 godown, GOODS-only catalogue, owner + sales staff
  trader      — small B2B trader: books on, batch lines, GSTIN customers, owner + acct + sales + viewer + import
  wholesale   — small wholesaler: books on, 3 godowns, price list, dunning config, owner + acct
  service     — non-stock services only: owner
  migration   — minimal shell for the day-zero cutover journey (the test loads the data)

Scale here is "realistic-small" (15-40 SKUs). Large-dataset behaviour is §H8 /
Phase 5, not this lane.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from masters.models import Customer, Product, Supplier

_ROLE = CompanyUser.Role


def _user(slug: str, tag: str) -> User:
    return User.objects.create_user(
        email=f"{tag}@{slug}.persona.test",
        password="StrongPass123!",
        full_name=f"{slug}-{tag}",
    )


def _member(company: Company, user: User, role: str, **caps) -> CompanyUser:
    cu = CompanyUser(company=company, user=user, role=role)
    for k, v in (CompanyUser.capability_defaults_for_role(role) or {}).items():
        setattr(cu, k, v)
    for k, v in caps.items():
        setattr(cu, k, v)
    cu.save()
    return cu


def _client(user: User) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _catalogue(company: Company, kind: str) -> list[Product]:
    n = {"retail": 15, "trader": 20, "wholesale": 25, "service": 6, "migration": 0}[kind]
    rate = ["18", "12", "5", "28", "0"]
    out = []
    for i in range(n):
        kw = {}
        if kind == "service":
            kw["product_type"] = "SERVICE"
            kw["track_inventory"] = False
        elif kind in ("trader", "wholesale") and i % 5 == 0:
            kw["track_batch"] = True
        out.append(
            Product.objects.create(
                company=company,
                name=f"{kind.title()} Item {i:02d}",
                sku=f"{kind[:3].upper()}-{i:03d}",
                gst_rate=Decimal(rate[i % len(rate)]),
                purchase_price=Decimal("60"),
                selling_price=Decimal("100"),
                reorder_level=Decimal("5") if kind == "wholesale" else Decimal("0"),
                **kw,
            )
        )
    return out


def seed_archetype(kind: str) -> SimpleNamespace:
    assert kind in ("retail", "trader", "wholesale", "service", "migration"), kind
    state = "Karnataka"
    books = kind in ("trader", "wholesale", "migration")
    company = Company.objects.create(
        name=f"{kind.title()} Co", state=state,
        gstin="29AAAAA0000A1ZY",
        accounting_enabled=books,
    )
    if books:
        from accounting.services import seed_chart_of_accounts

        seed_chart_of_accounts(company)

    ns = SimpleNamespace(kind=kind, company=company, warehouses=[], products=[],
                         customers=[], suppliers=[])

    # --- roles this archetype has ---
    owner = _user(kind, "owner")
    ns.owner, ns.owner_cu = owner, _member(company, owner, _ROLE.OWNER)
    ns.owner_client = _client(owner)

    if kind in ("retail", "trader", "wholesale"):
        sales = _user(kind, "sales")
        ns.sales, ns.sales_cu = sales, _member(company, sales, _ROLE.SALES_STAFF)
        ns.sales_client = _client(sales)

    if kind in ("trader", "wholesale", "migration"):
        acct = _user(kind, "acct")
        ns.acct, ns.acct_cu = acct, _member(company, acct, _ROLE.ACCOUNTANT)
        ns.acct_client = _client(acct)

    if kind == "trader":
        viewer = _user(kind, "viewer")
        ns.viewer, ns.viewer_cu = viewer, _member(company, viewer, _ROLE.VIEWER)
        ns.viewer_client = _client(viewer)
        importer = _user(kind, "import")
        ns.importer, ns.importer_cu = importer, _member(
            company, importer, _ROLE.SALES_STAFF, can_import=True
        )
        ns.importer_client = _client(importer)

    # --- godowns ---
    from inventory.services import InventoryService

    ns.warehouses = [InventoryService.default_warehouse(company)]
    if kind == "wholesale":
        for name, code in (("North", "NR"), ("South", "SR")):
            r = ns.owner_client.post(
                "/api/v1/inventory/warehouses/", {"name": name, "code": code}, format="json"
            )
            assert r.status_code == 201, r.data
        from inventory.models import Warehouse

        ns.warehouses = list(Warehouse.objects.filter(company=company).order_by("id"))

    # --- catalogue + parties (migration seeds nothing; the journey loads it) ---
    if kind != "migration":
        ns.products = _catalogue(company, kind)
        # GSTIN is unique per company; give registered parties distinct valid-shaped
        # numbers, leave the rest blank (B2CS-style).
        def _gstin(seq, pan_c="A"):
            return f"29{pan_c}{pan_c}{pan_c}{pan_c}{pan_c}{seq:04d}A1Z5"

        ns.customers = [
            Customer.objects.create(
                company=company, name=f"Cust {i}", state=state,
                gstin=_gstin(i) if i % 2 == 0 else "",
            )
            for i in range({"retail": 4, "trader": 10, "wholesale": 20, "service": 3}[kind])
        ]
        if kind in ("trader", "wholesale"):
            ns.suppliers = [
                Supplier.objects.create(company=company, name=f"Supp {i}", state=state,
                                        gstin=_gstin(i, pan_c="Z"))
                for i in range(5)
            ]

    return ns
