"""GST invariants that must hold for every financial document at rest.

The full place-of-supply matrix (state pairs x registration types x
SEZ/export/RCM) is a dedicated parametrized test (FG-2c,
tests/gst/test_place_of_supply_matrix.py), not a per-company sweep — these are
the cheap always-true checks.
"""

from __future__ import annotations

from decimal import Decimal

from .base import invariant
from .money import _document_total_models

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


@invariant(
    "gst.cgst_equals_sgst",
    consequence="A document has CGST != SGST — impossible for an Indian intra-state supply; the tax split is wrong.",
)
def cgst_equals_sgst(company) -> list[str]:
    out: list[str] = []
    for model in _document_total_models():
        try:
            qs = model.objects.filter(company=company)
        except Exception:
            continue
        for pk, c, s in qs.values_list("pk", "cgst_total", "sgst_total"):
            if abs((c or _ZERO) - (s or _ZERO)) > _CENT:
                out.append(f"{model.__name__}#{pk}: cgst_total {c} != sgst_total {s}")
    return out


@invariant(
    "gst.igst_xor_intrastate",
    consequence="A document carries both IGST and CGST/SGST — a supply is being taxed as inter- and intra-state at once.",
)
def igst_xor_intrastate(company) -> list[str]:
    out: list[str] = []
    for model in _document_total_models():
        try:
            qs = model.objects.filter(company=company)
        except Exception:
            continue
        for pk, i, c, s in qs.values_list("pk", "igst_total", "cgst_total", "sgst_total"):
            i = i or _ZERO
            intra = (c or _ZERO) + (s or _ZERO)
            if i > _CENT and intra > _CENT:
                out.append(
                    f"{model.__name__}#{pk}: igst_total {i} and cgst+sgst {intra} both non-zero"
                )
    return out
