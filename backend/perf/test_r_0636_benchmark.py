"""Nightly POS checkout baseline. Not collected by the pull-request suite (testpaths = tests).

Run with POS_BENCH=1. A full catalogue is POS_CATALOGUE=20000. The job records p95 and
fails when the new figure is more than 15% above qos/evidence/pos_checkout_baseline.json.
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "qos" / "evidence" / "pos_checkout_baseline.json"


def test_checkout_p95_on_the_catalogue(tenant_a):
    if os.environ.get("POS_BENCH") != "1":
        pytest.skip("Set POS_BENCH=1 to run the checkout baseline. It stays out of the pull-request suite.")
    from masters.models import Product
    from tests.conftest import add_stock, create_draft_invoice, make_customer

    from perf.checkout_bench import exceeds_baseline, p95_ms

    count = int(os.environ.get("POS_CATALOGUE") or "20000")
    existing = Product.objects.filter(company=tenant_a.company).count()
    now = timezone.now()
    if existing < count:
        Product.objects.bulk_create(
            [
                Product(
                    company=tenant_a.company,
                    name=f"SKU {i}",
                    sku=f"BENCH-{i}",
                    gst_rate=Decimal("18"),
                    purchase_price=Decimal("40"),
                    selling_price=Decimal("50"),
                    created_at=now,
                    updated_at=now,
                    created_by=tenant_a.owner,
                    updated_by=tenant_a.owner,
                )
                for i in range(existing, count)
            ],
            batch_size=1000,
        )
    products = list(Product.objects.filter(company=tenant_a.company, sku__startswith="BENCH-").order_by("id")[:3])
    if len(products) < 3:
        products = list(Product.objects.filter(company=tenant_a.company).order_by("id")[:3])
    for product in products:
        add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, name="Bench")
    lines = [
        {"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "18"}
        for product in products
    ]
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        draft = create_draft_invoice(tenant_a, customer, lines)
        done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
        assert done.status_code == 200, done.data
        samples.append((time.perf_counter() - started) * 1000)
    current = p95_ms(samples)
    recorded = {}
    if BASELINE.exists():
        recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline = recorded.get("baseline_p95_ms")
    if os.environ.get("POS_BENCH_RECORD") == "1" or baseline is None:
        recorded.update({
            "catalogue_skus": count,
            "cart_lines": 3,
            "target_p95_ms": 200,
            "baseline_p95_ms": round(current, 2),
            "samples_ms": [round(s, 2) for s in samples],
        })
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
        baseline = current
    assert not exceeds_baseline(current, float(baseline)), (
        f"p95 {current:.1f} ms is more than 15% above the baseline {baseline} ms"
    )
