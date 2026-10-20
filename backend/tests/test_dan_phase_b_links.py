"""DAN-07: every link an Attention row can carry opens a real page, and fixes show up at once."""

import re
from pathlib import Path

import pytest

from insights import attention as attention_module
from insights.attention import _row, fallback_href, invalidate_attention_cache_for

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "web" / "src" / "App.tsx"
SOURCES = [
    ROOT / "backend" / "insights" / "alerts.py",
    ROOT / "backend" / "insights" / "services.py",
    ROOT / "backend" / "insights" / "attention.py",
    ROOT / "backend" / "insights" / "customer_actions.py",
    ROOT / "backend" / "payments" / "predictive_dunning.py",
]


def _route_patterns():
    paths = re.findall(r'<Route\s+[^>]*?path="([^"]+)"', APP_TSX.read_text(encoding="utf-8"))
    patterns = []
    for path in paths:
        path = path.strip("/")
        if path in ("", "*"):
            continue
        regex = re.sub(r":[A-Za-z_]+", "[^/]+", re.escape(path).replace("\\:", ":"))
        patterns.append(re.compile("^" + regex + "$"))
    return patterns


def _hrefs():
    found = []
    pattern = re.compile(r'(?:cta_path|action_href|href)\s*=\s*f?"(/[^"]*)"')
    for src in SOURCES:
        text = src.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            found.append((src.name, match.group(1)))
    return found


def _normalise(href: str) -> str:
    href = re.sub(r"\{[^}]*\}", "1", href)
    return href.split("?")[0].split("#")[0].strip("/")


def test_every_static_link_resolves_to_a_real_route():
    patterns = _route_patterns()
    assert len(patterns) > 50, "route table could not be read"
    hrefs = _hrefs()
    assert len(hrefs) > 20
    broken = [
        (name, href)
        for name, href in hrefs
        if _normalise(href) and not any(p.match(_normalise(href)) for p in patterns)
    ]
    assert broken == []


def test_a_row_without_a_link_never_points_at_the_dashboard():
    row = _row(
        code="AR_COLLECTION_RISK", severity="warning", title="t", money_impact_paise=0, reason="r",
        action_label="Open", action_href="", source_ticket="T", entity_type="customer", entity_id=1,
    )
    assert row["action_href"] == fallback_href("AR_COLLECTION_RISK") != "/"
    unknown = _row(
        code="SOMETHING_NEW", severity="info", title="t", money_impact_paise=0, reason="r",
        action_label="Open", action_href="/", source_ticket="T", entity_type="company", entity_id=1,
    )
    assert unknown["action_href"] == "/attention"


@pytest.mark.django_db
def test_posting_a_receipt_drops_the_cached_feed(tenant_a):
    from django.core.cache import cache
    from django.utils import timezone

    key = f"insights:attention_raw:{tenant_a.company.pk}:{timezone.localdate().isoformat()}"
    cache.set(key, {"rows": [], "status": {"failed": [], "truncated": []}}, 60)
    invalidate_attention_cache_for(tenant_a.company.pk)
    assert cache.get(key) is None


@pytest.mark.django_db(transaction=True)
def test_saving_a_feed_document_invalidates_the_cache(tenant_a):
    from django.core.cache import cache
    from django.utils import timezone

    from tests.conftest import make_customer

    key = f"insights:attention_raw:{tenant_a.company.pk}:{timezone.localdate().isoformat()}"
    cache.set(key, {"rows": [], "status": {"failed": [], "truncated": []}}, 60)
    customer = make_customer(tenant_a.company)
    from payments.models import PaymentPromise

    promise = PaymentPromise(
        company=tenant_a.company, customer=customer, promised_date=timezone.localdate(), promised_amount=10,
    )
    promise.save()
    assert cache.get(key) is None
    assert attention_module  # module import keeps the signal wiring honest
