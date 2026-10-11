"""Money In profile: seed receipts (with allocations and UTRs) and time list, search, totals, export.

Reproduces the numbers recorded in docs/plans/MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md (WP-15). It is
a developer tool, not a test: it writes tens of thousands of rows, so point it at a throwaway
PostgreSQL database that has been migrated (``DATABASE_URL`` + ``manage.py migrate``).

    DATABASE_URL=postgres://... DJANGO_SETTINGS_MODULE=config.settings_test \\
    PYTEST_KEEP_DATABASE_URL=1 python -m perf.receipts_profile --tenants 3 --per-tenant 135000

What it does, per tenant: creates a company, a few hundred customers, ``--per-tenant`` posted
receipts spread over three years (UPI receipts carry a UTR, so the duplicate-UTR lookup is
exercised; ``--allocated`` of them also carry a live allocation), then ANALYZEs and times, with
the API serializers and permissions in the loop (through the test client):

* the first page of the list, unfiltered and with each search kind
* ``summary/`` for the current month and for the full range
* ``export/`` of one month
* with ``--explain``, the ``EXPLAIN (ANALYZE, BUFFERS)`` of the summary aggregate

Each timing is the best of ``--repeat`` runs, in milliseconds, printed as a table and as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, timedelta
from decimal import Decimal


def _setup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    os.environ.setdefault("PYTEST_KEEP_DATABASE_URL", "1")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import django

    django.setup()


def seed_tenant(slug: str, receipts: int, allocated_share: float, customers: int, rng: random.Random):
    from django.utils import timezone
    from rest_framework.test import APIClient

    from accounts.models import Company, CompanyUser, User
    from masters.models import Customer
    from payments.models import BankAccount, CustomerReceipt, PaymentAllocation
    from sales.models import SalesInvoice

    owner = User.objects.create_user(
        email=f"owner@{slug}.perf", password="StrongPass123!", full_name=f"{slug} owner"
    )
    company = Company.objects.create(name=f"{slug} Perf Traders", state="Karnataka", gstin="29AAAAA0000A1ZY")
    CompanyUser.objects.create(company=company, user=owner, role=CompanyUser.Role.OWNER, can_export=True)
    bank = BankAccount.objects.create(company=company, name="Perf bank", account_type="CURRENT", is_default=True)
    people = Customer.objects.bulk_create(
        [Customer(company=company, name=f"{slug} customer {i:04d}", state="Karnataka", phone=f"98{i:08d}")
         for i in range(customers)]
    )
    today = timezone.localdate()
    rows = []
    for i in range(receipts):
        on = today - timedelta(days=rng.randint(0, 3 * 365))
        mode = rng.choice(["CASH", "UPI", "UPI", "BANK", "CHEQUE"])
        rows.append(CustomerReceipt(
            company=company, customer=rng.choice(people), number=f"RCT-{slug[:3].upper()}-{i:07d}",
            amount=Decimal(rng.randint(100, 50000)), mode=mode, receipt_date=on,
            utr=f"UTR{slug[:2].upper()}{i:09d}" if mode in ("UPI", "BANK") else "",
            bank_account=bank if mode in ("UPI", "BANK") else None,
            reference=f"REF{i:07d}" if mode == "CHEQUE" else "",
            cheque_number=str(rng.randint(100000, 999999)) if mode == "CHEQUE" else "",
            cheque_status="CLEARED" if mode == "CHEQUE" else "",
        ))
        if len(rows) >= 5000:
            CustomerReceipt.objects.bulk_create(rows)
            rows = []
    if rows:
        CustomerReceipt.objects.bulk_create(rows)
    # Live allocations need an invoice: give each allocated receipt a minimal completed one.
    ids = list(
        CustomerReceipt.objects.filter(company=company).order_by("id").values_list("id", "customer_id", "amount")
    )
    chosen = rng.sample(ids, k=int(len(ids) * allocated_share))
    batch = []
    for receipt_id, customer_id, amount in chosen:
        invoice = SalesInvoice(
            company=company, customer_id=customer_id, status="COMPLETED", grand_total=amount,
            invoice_date=today, number=f"INV-{slug[:3].upper()}-{receipt_id}",
        )
        batch.append((receipt_id, amount, invoice))
        if len(batch) >= 2000:
            _flush_alloc(company, batch)
            batch = []
    if batch:
        _flush_alloc(company, batch)
    client = APIClient()
    client.force_authenticate(user=owner)
    return company, client, PaymentAllocation


def _flush_alloc(company, batch):
    from payments.models import PaymentAllocation
    from sales.models import SalesInvoice

    invoices = SalesInvoice.objects.bulk_create([inv for _, _, inv in batch])
    PaymentAllocation.objects.bulk_create([
        PaymentAllocation(company=company, receipt_id=rid, sales_invoice=inv, amount=amount)
        for (rid, amount, _), inv in zip(batch, invoices, strict=True)
    ])


def existing_tenant(slug: str):
    from rest_framework.test import APIClient

    from accounts.models import Company, CompanyUser

    company = Company.objects.get(name=f"{slug} Perf Traders")
    owner = CompanyUser.objects.get(company=company).user
    client = APIClient()
    client.force_authenticate(user=owner)
    return company, client


def best_ms(call, repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        call()
        best = min(best, (time.perf_counter() - started) * 1000)
    return round(best, 1)


def profile(client, repeat: int, sample_utr: str, sample_number: str, sample_name: str, prefix_len: int = 12) -> dict:
    url = "/api/v1/payments/receipts/"
    today = date.today()
    month = {"date_from": today.replace(day=1).isoformat(), "date_to": today.isoformat()}
    out = {}

    def get(path, params=None):
        resp = client.get(path, params or {})
        assert resp.status_code == 200, (path, params, resp.status_code)
        if hasattr(resp, "streaming_content"):
            b"".join(resp.streaming_content)
        return resp

    out["list_first_page"] = best_ms(lambda: get(url, {"page_size": 50}), repeat)
    out["list_page_100"] = best_ms(lambda: get(url, {"page_size": 100}), repeat)
    out["search_receipt_number"] = best_ms(lambda: get(url, {"q": sample_number}), repeat)
    out["search_utr_prefix"] = best_ms(lambda: get(url, {"q": sample_utr[:prefix_len]}), repeat)
    out["search_customer_name"] = best_ms(lambda: get(url, {"q": sample_name}), repeat)
    out["search_phone"] = best_ms(lambda: get(url, {"q": "9800001"}), repeat)
    out["summary_all"] = best_ms(lambda: get(f"{url}summary/"), repeat)
    out["summary_month"] = best_ms(lambda: get(f"{url}summary/", month), repeat)
    out["export_month"] = best_ms(lambda: get(f"{url}export/", month), 1)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenants", type=int, default=3)
    parser.add_argument("--per-tenant", type=int, default=135000)
    parser.add_argument("--allocated", type=float, default=0.6, help="share of receipts with a live allocation")
    parser.add_argument("--customers", type=int, default=400)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--no-seed", action="store_true", help="time the tenants a previous run already seeded")
    args = parser.parse_args(argv)
    _setup()
    from django.db import connection

    rng = random.Random(args.seed)  # noqa: S311 - a reproducible profile, not a secret
    results = {}
    for index in range(args.tenants):
        slug = f"perf{index}"
        started = time.perf_counter()
        if args.no_seed:
            company, client = existing_tenant(slug)
        else:
            company, client, _ = seed_tenant(slug, args.per_tenant, args.allocated, args.customers, rng)
            print(f"[{slug}] seeded {args.per_tenant} receipts in {time.perf_counter() - started:.0f}s", flush=True)
        from payments.models import CustomerReceipt

        sample = CustomerReceipt.objects.filter(company=company).exclude(utr="").first()
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE payments_customerreceipt")
            cursor.execute("ANALYZE payments_paymentallocation")
            cursor.execute("ANALYZE masters_customer")
        results[slug] = profile(client, args.repeat, sample.utr, sample.number, sample.customer.name)
        if args.explain:
            today = date.today()
            with connection.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN (ANALYZE, BUFFERS) SELECT COUNT(*), SUM(amount), SUM(tds_deducted) "
                    "FROM payments_customerreceipt WHERE company_id = %s AND receipt_date >= %s AND receipt_date <= %s",
                    [company.id, today.replace(day=1), today],
                )
                print("\n".join(row[0] for row in cursor.fetchall()))
    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
