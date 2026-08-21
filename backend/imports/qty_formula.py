"""Format-agnostic billed-qty resolution for purchase/sales bill import.

Vendors print quantity in many layouts (plain Qty, Box×Pack, Cs/Pcs/UPC,
strips/box, kg, dozen, …). We never hard-code a vendor: extra numeric columns
are treated as a pool, candidate formulas are scored against each line's
printed amount × unit price, and the winner is stored on the vendor template.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Keep enum values in sync with SupplierBillTemplate.LineTotalFormula without
# importing Django models from this helper (avoids app-loading cycles).
FORMULA_SIMPLE = "SIMPLE"
FORMULA_CASE_UNITS_PLUS_LOOSE = "CASE_UNITS_PLUS_LOOSE"

# Columns that are money (or tax), never factors of billed quantity.
_MONEY_TOKENS = (
    "mrp", "rate", "price", "amount", "amt", "gross", "taxable", "net",
    "disc", "discount", "sch", "scheme_amt", "tax", "gst", "cgst", "sgst",
    "igst", "cess", "tcs", "value", "total",
)
# Quantity-like columns that are NOT billed qty (free/FOC/bonus).
_SKIP_COUNT_TOKENS = ("free", "foc", "bonus", "scheme_qty", "sample")
_SKIP_COUNT_KEYS = {"sl", "si", "sno", "sr", "s_no", "line_no", "sn"}

_CANONICAL_LINE_KEYS = {
    "si", "sl", "name", "sku", "hsn", "hsn_code", "quantity", "unit_price",
    "unitprice", "gst_rate", "gstrate", "mrp", "include", "confidence",
    "flags", "warnings", "printed_gross_amt", "printed_taxable_amt",
    "cs", "upc", "extras", "pcode", "pc_price",
}

_TOKEN_LABELS = {
    "quantity": "Qty / Pcs / Nos",
    "cs": "Cs / Cases",
    "upc": "UPC",
    "boxes": "Boxes",
    "box": "Box",
    "ctn": "Cartons",
    "pack": "Pack",
    "strips": "Strips",
    "dozen": "Dozen",
    "doz": "Doz",
    "kg": "Kg",
    "ltr": "Ltr",
}


def _safe_decimal(value) -> Decimal:
    try:
        text = str(value if value not in (None, "") else "0").strip()
        return Decimal(text) if text else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _norm_key(key: str) -> str:
    return str(key or "").strip().lower().replace(" ", "_").replace("-", "_")


def _is_money_key(key: str) -> bool:
    k = _norm_key(key)
    if k in ("upc", "cs"):
        return False
    return any(tok in k for tok in _MONEY_TOKENS)


def _is_skipped_count_key(key: str) -> bool:
    k = _norm_key(key)
    if k in _SKIP_COUNT_KEYS:
        return True
    return any(tok in k for tok in _SKIP_COUNT_TOKENS)


def collect_extras(raw_line: dict) -> dict[str, str]:
    """Pull pack/qty side-columns from LLM `raw_columns` / top-level leftovers."""
    extras: dict[str, str] = {}

    def _put(key, value):
        if value in (None, "") or _is_money_key(key) or _is_skipped_count_key(key):
            return
        extras[_norm_key(key)] = str(value).strip().replace(",", "")

    raw_cols = raw_line.get("raw_columns") or raw_line.get("extras") or {}
    if isinstance(raw_cols, dict):
        for key, value in raw_cols.items():
            _put(key, value)
    for key in ("cs", "upc", "boxes", "box", "ctn", "cartons", "pack", "strips", "dozen", "doz"):
        if raw_line.get(key) not in (None, ""):
            _put(key, raw_line.get(key))
    for key, value in raw_line.items():
        if key in _CANONICAL_LINE_KEYS or not isinstance(key, str):
            continue
        if isinstance(value, dict):
            continue
        _put(key, value)
    return extras


def count_pool(line: dict) -> dict[str, Decimal]:
    pool: dict[str, Decimal] = {}
    if line.get("quantity") not in (None, ""):
        pool["quantity"] = _safe_decimal(line.get("quantity"))
    extras = line.get("extras") if isinstance(line.get("extras"), dict) else {}
    if not extras:
        extras = collect_extras(line)
    for key, value in extras.items():
        nk = _norm_key(key)
        if nk in pool or _is_money_key(nk) or _is_skipped_count_key(nk):
            continue
        if value in (None, ""):
            continue
        pool[nk] = _safe_decimal(value)
    for key in ("cs", "upc"):
        if line.get(key) not in (None, "") and key not in pool:
            pool[key] = _safe_decimal(line.get(key))
    return pool


def printed_total(line: dict) -> Decimal:
    gross = _safe_decimal(line.get("printed_gross_amt"))
    if gross:
        return gross
    extras = line.get("extras") if isinstance(line.get("extras"), dict) else {}
    for key in ("taxable_amt", "taxable", "amount", "net_amt", "printed_taxable_amt"):
        value = line.get(key, extras.get(key) if extras else None)
        amount = _safe_decimal(value)
        if amount:
            return amount
    return Decimal("0")


def eval_formula(formula: str, pool: dict[str, Decimal]) -> Decimal | None:
    """Evaluate a restricted expression: a | a*b | a+b | a*b+c (no parentheses)."""
    expr = (formula or "").strip().lower()
    if not expr:
        return None
    total = Decimal("0")
    for addend in expr.split("+"):
        prod = Decimal("1")
        for factor in addend.split("*"):
            token = factor.strip()
            if token not in pool:
                return None
            prod *= pool[token]
        total += prod
    return total


def _complexity(formula: str) -> int:
    return formula.count("*") + formula.count("+")


def _union_keys(lines: list[dict]) -> set[str]:
    keys: set[str] = set()
    for line in lines:
        keys.update(count_pool(line).keys())
    return keys


def candidate_formulas(keys: set[str]) -> list[str]:
    """Bounded set of qty expressions from whatever count columns this bill has."""
    formulas: list[str] = []
    if "quantity" in keys:
        formulas.append("quantity")
    extras = sorted(k for k in keys if k != "quantity")
    formulas.extend(extras)
    for i, a in enumerate(extras):
        if "quantity" in keys:
            formulas.append(f"{a}*quantity")
            formulas.append(f"{a}+quantity")
        for b in extras[i + 1 :]:
            formulas.append(f"{a}*{b}")
            if "quantity" in keys:
                formulas.append(f"{a}*{b}+quantity")
    # Preserve order, cap so a 15-column sheet cannot explode.
    seen: set[str] = set()
    out: list[str] = []
    for formula in formulas:
        if formula in seen:
            continue
        seen.add(formula)
        out.append(formula)
        if len(out) >= 40:
            break
    return out


def formula_label(formula: str) -> str:
    def token(part: str) -> str:
        return _TOKEN_LABELS.get(part, part.replace("_", " ").title())

    addends = []
    for addend in formula.split("+"):
        factors = [token(f.strip()) for f in addend.split("*")]
        addends.append(" x ".join(factors) if len(factors) > 1 else factors[0])
    if len(addends) == 1:
        if formula == "quantity":
            return "Use the Qty / Pcs / Nos column as billed quantity"
        return addends[0]
    return " + ".join(addends)


def resolve_formula_expr(answers: dict | None) -> str:
    answers = answers or {}
    raw = str(answers.get("qty_formula") or "").strip()
    if raw:
        return raw
    if (
        answers.get("upc_meaning") == "units_per_case"
        and answers.get("pcs_meaning") == "loose_plus_cases"
    ):
        return "cs*upc+quantity"
    return "quantity"


def formula_enum(expr: str) -> str:
    if expr in ("cs*upc+quantity", "cs*upc+pcs"):
        return FORMULA_CASE_UNITS_PLUS_LOOSE
    return FORMULA_SIMPLE


def _formulas_equivalent(left: str, right: str, lines: list[dict]) -> bool:
    compared = 0
    for line in lines:
        pool = count_pool(line)
        qty_l = eval_formula(left, pool)
        qty_r = eval_formula(right, pool)
        if qty_l is None or qty_r is None:
            continue
        compared += 1
        if qty_l != qty_r:
            return False
    return compared > 0


def infer_qty_formula(lines: list[dict], *, tolerance: Decimal) -> str | None:
    """Return a qty expression when printed amounts uniquely pick one; else None."""
    keys = _union_keys(lines)
    extras = {k for k in keys if k != "quantity"}
    if not extras:
        return None
    formulas = candidate_formulas(keys)
    scores = {formula: 0 for formula in formulas}
    unique = {formula: 0 for formula in formulas}
    informative = 0
    for line in lines:
        price = _safe_decimal(line.get("unit_price"))
        total = printed_total(line)
        if not price or not total:
            continue
        pool = count_pool(line)
        matches = []
        for formula in formulas:
            qty = eval_formula(formula, pool)
            if qty is None or qty <= 0:
                continue
            if abs(qty * price - total) <= tolerance:
                matches.append(formula)
                scores[formula] += 1
        if not matches:
            continue
        informative += 1
        if len(matches) == 1:
            unique[matches[0]] += 1
    if informative == 0:
        return None
    ranked = sorted(
        formulas,
        key=lambda formula: (scores[formula], unique[formula], -_complexity(formula)),
        reverse=True,
    )
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    if scores[best] == 0:
        return None
    if second and scores[second] == scores[best] and unique[best] == unique[second]:
        if _complexity(best) != _complexity(second):
            return best if _complexity(best) < _complexity(second) else second
        if _formulas_equivalent(best, second, lines):
            return best
        return None
    if best == "quantity" and unique[best] == 0 and second and unique[second] >= 1:
        return second
    return best


def detect_qty_clarifications(lines: list[dict]) -> list[dict]:
    """One document-level question whose options are derived from *this* bill's columns."""
    keys = _union_keys(lines)
    extras = sorted(k for k in keys if k != "quantity")
    if not extras:
        return []
    options = [{"value": "quantity", "label": formula_label("quantity")}]
    if len(extras) >= 2:
        a, b = extras[0], extras[1]
        options.append({
            "value": f"{a}*{b}+quantity",
            "label": formula_label(f"{a}*{b}+quantity"),
        })
        options.append({"value": f"{a}*{b}", "label": formula_label(f"{a}*{b}")})
    else:
        a = extras[0]
        options.append({
            "value": f"{a}*quantity" if "quantity" in keys else a,
            "label": formula_label(f"{a}*quantity" if "quantity" in keys else a),
        })
        if "quantity" in keys:
            options.append({
                "value": f"{a}+quantity",
                "label": formula_label(f"{a}+quantity"),
            })
    seen: set[str] = set()
    deduped = []
    for option in options:
        if option["value"] in seen:
            continue
        seen.add(option["value"])
        deduped.append(option)
    return [{
        "field": "qty_formula",
        "question": "How should billed quantity be calculated on this vendor's bill?",
        "options": deduped[:3],
        "answer": None,
    }]


def apply_qty_formula(lines: list[dict], answers: dict, *, tolerance: Decimal) -> str:
    """Rewrite line.quantity from the resolved expression, then flag printed-total mismatches."""
    expr = resolve_formula_expr(answers)
    enum_key = formula_enum(expr)
    for line in lines:
        flags: list[str] = []
        pool = count_pool(line)
        derived = eval_formula(expr, pool)
        if derived is not None and derived > 0:
            line["quantity"] = str(derived)
            qty = derived
        else:
            qty = _safe_decimal(line.get("quantity"))
        price = _safe_decimal(line.get("unit_price"))
        total = printed_total(line)
        if qty and price and total:
            recomputed = qty * price
            if abs(recomputed - total) > tolerance:
                flags.append(
                    f"Recomputed gross amount ₹{recomputed} doesn't match the bill's "
                    f"printed ₹{total} for this line — check quantity/price."
                )
        line["flags"] = flags
    return enum_key
