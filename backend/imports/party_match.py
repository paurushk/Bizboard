"""Party and product matching for bill imports.

Used at preview time (so the reviewer sees who/what a bill will bind to) and at
commit time (so the same rules decide what is bound or created). Matching never
auto-binds on a fuzzy score: fuzzy hits are only offered as candidates.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from masters.models import Customer, Product, Supplier

_LEGAL_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|co|company|corp|corporation|and|the)\b"
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_UNSAFE_NAME_CHARS = re.compile(r"[<>\x00-\x1f]")

FUZZY_CANDIDATE_MIN = 0.80
FUZZY_CANDIDATES = 3


def normalize_name(value: str) -> str:
    text = str(value or "").casefold()
    text = _LEGAL_SUFFIX.sub(" ", text)
    return _NON_ALNUM.sub(" ", text).strip()


def sanitize_party_name(value: str) -> str:
    """Strip OCR noise that the party serializer rejects (`<`, `>`, controls)."""
    return " ".join(_UNSAFE_NAME_CHARS.sub(" ", str(value or "")).split()).strip()


def _score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _scored(norm: str, rows, threshold: float):
    """[(score, obj)] for rows whose normalised name is similar enough.

    `rows` is an iterable of (normalised_name, obj). Uses the cheap upper-bound
    ratios first so a large catalog stays fast.
    """
    matcher = SequenceMatcher()
    matcher.set_seq2(norm)
    out = []
    for cand_norm, obj in rows:
        if not cand_norm:
            continue
        matcher.set_seq1(cand_norm)
        if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
            continue
        score = matcher.ratio()
        if score >= threshold:
            out.append((score, obj))
    out.sort(key=lambda pair: -pair[0])
    return out


def _party_row(obj) -> dict:
    return {"id": obj.pk, "name": obj.name, "gstin": getattr(obj, "gstin", "") or ""}


def _match_party(queryset, *, gstin: str, name: str, extracted_name: str, extracted_gstin: str) -> dict:
    """Shared matcher over an already-filtered (active, non-walk-in) queryset."""
    result = {
        "status": "none",
        "id": None,
        "candidates": [],
        "extracted": {"name": extracted_name, "gstin": extracted_gstin},
        "will_create": bool(name),
        "notes": [],
    }
    by_gstin = queryset.filter(gstin__iexact=gstin).first() if gstin else None
    norm = normalize_name(name)
    by_name = None
    if norm:
        # Exact normalised match (not an icontains scan): compare in Python over
        # the company's parties; party masters are small relative to products.
        for obj in queryset.only("id", "name", "gstin").iterator():
            if normalize_name(obj.name) == norm:
                by_name = obj
                break
    if by_gstin and by_name and by_gstin.pk != by_name.pk:
        result.update(status="conflict", will_create=False)
        result["candidates"] = [_party_row(by_gstin), _party_row(by_name)]
        result["notes"].append("GSTIN and name match different parties — pick one.")
        return result
    hit = by_gstin or by_name
    if hit is not None:
        result.update(
            status="matched",
            id=hit.pk,
            will_create=False,
            # Only an exact GSTIN (or a name match when the bill had no GSTIN)
            # is safe to bind without asking.
            exact=bool(by_gstin) or not gstin,
        )
        result["candidates"] = [_party_row(hit)]
        return result
    if norm:
        scored = _scored(
            norm,
            ((normalize_name(o.name), o) for o in queryset.only("id", "name", "gstin").iterator()),
            FUZZY_CANDIDATE_MIN,
        )
        if scored:
            result["status"] = "candidates"
            result["candidates"] = [
                {**_party_row(obj), "score": round(score, 2)}
                for score, obj in scored[:FUZZY_CANDIDATES]
            ]
    return result


def match_customer(company, *, gstin: str, name: str) -> dict:
    gstin = str(gstin or "").strip().upper()
    clean = sanitize_party_name(name)
    qs = Customer.objects.filter(
        company=company, status=Customer.Status.ACTIVE, is_pos_walk_in=False
    )
    result = _match_party(qs, gstin=gstin, name=clean, extracted_name=clean, extracted_gstin=gstin)
    # Tell the reviewer when the bill names someone we deliberately won't bind.
    blocked = None
    if gstin:
        blocked = (
            Customer.objects.filter(company=company, gstin__iexact=gstin)
            .exclude(status=Customer.Status.ACTIVE)
            .first()
        )
    if blocked is not None and result["status"] == "none":
        result["notes"].append(
            f"{blocked.name} matches this GSTIN but is {blocked.status.lower()} — "
            "reactivate it or pick another customer."
        )
        result["will_create"] = False
        result["status"] = "inactive_match"
        result["candidates"] = [_party_row(blocked)]
    walk_in = (
        Customer.objects.filter(company=company, is_pos_walk_in=True).first()
        if clean
        else None
    )
    if walk_in is not None and normalize_name(walk_in.name) == normalize_name(clean):
        result["notes"].append("This looks like the walk-in/cash customer; pick a real customer.")
    return result


def match_supplier(company, *, gstin: str, name: str) -> dict:
    gstin = str(gstin or "").strip().upper()
    clean = sanitize_party_name(name)
    qs = Supplier.objects.filter(company=company, is_active=True)
    result = _match_party(qs, gstin=gstin, name=clean, extracted_name=clean, extracted_gstin=gstin)
    if gstin and result["status"] == "none":
        inactive = Supplier.objects.filter(company=company, gstin__iexact=gstin, is_active=False).first()
        if inactive is not None:
            result.update(
                status="inactive_match", will_create=False, candidates=[_party_row(inactive)],
                notes=[f"{inactive.name} matches this GSTIN but is inactive — reactivate it or pick another supplier."],
            )
    return result


# --- products -------------------------------------------------------------


def build_catalog(company) -> dict:
    """One query for the whole catalog so an 80-line bill does not run 240."""
    by_sku: dict[str, Product] = {}
    by_name: dict[str, Product] = {}
    by_id: dict[int, Product] = {}
    rows = []
    for product in Product.objects.filter(company=company).only(
        "id", "name", "sku", "barcode", "track_batch", "cess_rate", "cess_amount"
    ).iterator():
        by_id[product.pk] = product
        if product.sku:
            by_sku.setdefault(product.sku.casefold(), product)
        if product.barcode:
            by_sku.setdefault(product.barcode.casefold(), product)
        norm = normalize_name(product.name)
        if norm:
            by_name.setdefault(norm, product)
        rows.append((norm, product))
    return {"by_sku": by_sku, "by_name": by_name, "by_id": by_id, "rows": rows}


def match_product(line: dict, catalog: dict) -> dict:
    sku = str(line.get("sku") or "").strip().casefold()
    name = str(line.get("name") or "").strip()
    if sku and sku in catalog["by_sku"]:
        product = catalog["by_sku"][sku]
        return product_match_row("matched", product, "sku", 1.0)
    norm = normalize_name(name)
    if norm and norm in catalog["by_name"]:
        return product_match_row("matched", catalog["by_name"][norm], "name", 1.0)
    candidates = _scored(norm, catalog["rows"], FUZZY_CANDIDATE_MIN) if norm else []
    if candidates:
        return {
            "status": "candidates",
            "product_id": None,
            "candidates": [
                {"id": p.pk, "name": p.name, "sku": p.sku, "score": round(s, 2)}
                for s, p in candidates[:FUZZY_CANDIDATES]
            ],
        }
    return {"status": "none", "product_id": None, "candidates": []}


def product_match_row(status: str, product: Product, method: str, score: float) -> dict:
    return {
        "status": status,
        "product_id": product.pk,
        "name": product.name,
        "method": method,
        "score": score,
        "track_batch": bool(getattr(product, "track_batch", False)),
        "cess_rate": str(product.cess_rate) if getattr(product, "cess_rate", None) else "",
        "cess_amount": str(product.cess_amount) if getattr(product, "cess_amount", None) else "",
        "candidates": [],
    }
