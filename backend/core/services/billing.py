"""
Invoice Service — shared tax/discount/rounding math used by sales & purchases
(E3.2, E4.3). GST split: intra-state = CGST+SGST, inter-state = IGST.
"""

from decimal import ROUND_HALF_UP, Decimal

from core.exceptions import BusinessRuleError

TWO_PLACES = Decimal("0.01")
RUPEE = Decimal("1")

DISCOUNT_AFTER_TAX = "AFTER_TAX"
DISCOUNT_BEFORE_TAX = "BEFORE_TAX"

# BB-000063: canonical Indian state/UT name + common abbreviation → GST state code.
IN_STATE_NAME_TO_CODE = {
    "andaman and nicobar islands": "35",
    "andaman & nicobar islands": "35",
    "andhra pradesh": "37",
    "arunachal pradesh": "12",
    "assam": "18",
    "bihar": "10",
    "chandigarh": "04",
    "chhattisgarh": "22",
    "dadra and nagar haveli and daman and diu": "26",
    "dadra and nagar haveli": "26",
    "daman and diu": "26",
    "delhi": "07",
    "nct of delhi": "07",
    "goa": "30",
    "gujarat": "24",
    "haryana": "06",
    "himachal pradesh": "02",
    "jammu and kashmir": "01",
    "jammu & kashmir": "01",
    "jharkhand": "20",
    "karnataka": "29",
    "kerala": "32",
    "ladakh": "38",
    "lakshadweep": "31",
    "madhya pradesh": "23",
    "maharashtra": "27",
    "manipur": "14",
    "meghalaya": "17",
    "mizoram": "15",
    "nagaland": "13",
    "odisha": "21",
    "orissa": "21",
    "puducherry": "34",
    "pondicherry": "34",
    "punjab": "03",
    "rajasthan": "08",
    "sikkim": "11",
    "tamil nadu": "33",
    "telangana": "36",
    "tripura": "16",
    "uttar pradesh": "09",
    "uttarakhand": "05",
    "west bengal": "19",
    # Common abbreviations
    "an": "35",
    "ap": "37",
    "ar": "12",
    "as": "18",
    "br": "10",
    "ch": "04",
    "cg": "22",
    "ct": "22",
    "dn": "26",
    "dd": "26",
    "dl": "07",
    "ga": "30",
    "gj": "24",
    "hr": "06",
    "hp": "02",
    "jk": "01",
    "jh": "20",
    "ka": "29",
    "kl": "32",
    "la": "38",
    "ld": "31",
    "mp": "23",
    "mh": "27",
    "mn": "14",
    "ml": "17",
    "mz": "15",
    "nl": "13",
    "od": "21",
    "or": "21",
    "py": "34",
    "pb": "03",
    "rj": "08",
    "sk": "11",
    "tn": "33",
    "ts": "36",
    "tg": "36",
    "tr": "16",
    "up": "09",
    "uk": "05",
    "ua": "05",
    "wb": "19",
    # Export / other territory (POS code 96)
    "other territory": "96",
    "other country": "96",
    "foreign": "96",
    "export": "96",
}

VALID_GST_STATE_CODES = frozenset(set(IN_STATE_NAME_TO_CODE.values()) | {"96", "97"})


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def extract_state_code(value: str | None) -> str | None:
    """
    Canonical GST state code from a full GSTIN, exact 2-digit code, or mapped name/abbr.
    Does not treat arbitrary free-text prefixes like "11xxxx" as state codes.
    """
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    # Full GSTIN: digits 0–1 are the state code when recognised.
    if len(trimmed) == 15 and trimmed[:2].isdigit():
        code = trimmed[:2]
        return code if code in VALID_GST_STATE_CODES else None
    # Exact 2-digit place-of-supply / state code only.
    if len(trimmed) == 2 and trimmed.isdigit() and trimmed in VALID_GST_STATE_CODES:
        return trimmed
    key = " ".join(trimmed.lower().replace(".", "").split())
    return IN_STATE_NAME_TO_CODE.get(key)


def place_of_supply_known(*, party_state: str = "", party_gstin: str = "") -> bool:
    """True when party has a GSTIN state code or a state name mappable to one.

    BB-000365: previously any non-empty free-text state counted as "known",
    even when it couldn't be mapped to a GST state code — that unmapped text
    then flowed straight into GSTR/e-Invoice place-of-supply fields, which
    reject it. The Complete gate must require an actually-mappable code.
    """
    if extract_state_code(party_gstin) is not None:
        return True
    if extract_state_code(party_state) is not None:
        return True
    return False


def is_intra_state(
    company_state: str,
    party_state: str,
    *,
    company_gstin: str = "",
    party_gstin: str = "",
) -> bool:
    """
    Compare normalized GST state codes (from GSTIN digits or name map).
    Missing party state/GSTIN still returns True for calc fallback — callers must
    gate Complete via place_of_supply_known / company.assume_local_state_for_blank_party.
    """
    # Prefer GSTIN state digits when present; else map state name/abbr to code.
    company_code = extract_state_code(company_gstin) or extract_state_code(company_state)
    party_code = extract_state_code(party_gstin) or extract_state_code(party_state)
    if company_code and party_code:
        return company_code == party_code

    a = (company_state or "").strip().lower()
    b = (party_state or "").strip().lower()
    # BB-000638: blank party POS is unknown — not silent intra.
    if not b and not party_code:
        return False
    if not a and not company_code:
        return False
    if not b or not a:
        return False
    return a == b


def _apply_line_tax(item, taxable: Decimal, rate: Decimal, *, tax_enabled: bool, intra_state: bool):
    tax = taxable * rate / Decimal("100") if tax_enabled else Decimal("0")
    if intra_state:
        half = q2(tax / 2)
        item.cgst = half
        item.sgst = q2(tax) - half  # residual so halves sum to q2(tax)
        item.igst = Decimal("0.00")
    else:
        item.cgst = Decimal("0.00")
        item.sgst = Decimal("0.00")
        item.igst = q2(tax)
    item.taxable_amount = taxable
    cess_rate = Decimal(str(getattr(item, "cess_rate", 0) or 0))
    cess_specific = Decimal(str(getattr(item, "cess_amount", 0) or 0))
    if hasattr(item, "cess"):
        if tax_enabled:
            qty = Decimal(str(getattr(item, "quantity", 0) or 0))
            ad_valorem = q2(taxable * cess_rate / Decimal("100")) if cess_rate else Decimal("0.00")
            specific = q2(qty * cess_specific) if cess_specific > 0 else Decimal("0.00")
            item.cess = q2(ad_valorem + specific)
        else:
            item.cess = Decimal("0.00")
        item.line_total = q2(taxable + item.cgst + item.sgst + item.igst + item.cess)
    else:
        item.line_total = q2(taxable + item.cgst + item.sgst + item.igst)


def extract_exclusive_from_inclusive_line(
    *,
    quantity: Decimal,
    unit_price_inclusive: Decimal,
    discount_percent: Decimal,
    gst_rate: Decimal,
    cess_rate: Decimal = Decimal("0"),
    cess_amount: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal]:
    """
    Tax-inclusive → exclusive: discount on inclusive gross, extract tax once
    from discounted inclusive net. Returns (exclusive_unit_price, taxable).
    BB-000611: denominator includes cess so MRP embedding GST+cess extracts once.
    Specific per-unit cess_amount is peeled off the inclusive net before the rate extract.
    """
    qty = Decimal(quantity)
    if qty <= 0:
        return q2(Decimal(unit_price_inclusive)), Decimal("0.00")
    line_gross_inclusive = q2(qty * Decimal(unit_price_inclusive))
    discount_amt = q2(line_gross_inclusive * Decimal(discount_percent) / Decimal("100"))
    net_inclusive = q2(line_gross_inclusive - discount_amt)
    specific = q2(qty * Decimal(str(cess_amount or 0)))
    if specific > 0:
        net_inclusive = q2(max(Decimal("0.00"), net_inclusive - specific))
    rate = Decimal(gst_rate) + Decimal(str(cess_rate or 0))
    if rate > 0:
        taxable = q2(net_inclusive * Decimal("100") / (Decimal("100") + rate))
    else:
        taxable = net_inclusive
    exclusive_unit = q2(taxable / qty) if qty else Decimal("0.00")
    return exclusive_unit, taxable


def apply_inclusive_prices_to_items(items, *, price_mode: str) -> list[Decimal]:
    """
    When price_mode=INCLUSIVE, derive exclusive unit_price from unit_price_inclusive
    (never from unit_price — that would double-extract on re-save).

    Temporarily zeroes discount_percent for the exclusive pipeline; returns the
    original discounts so the caller can restore them for persistence.
    """
    if (price_mode or "EXCLUSIVE") != "INCLUSIVE":
        return []
    stashed: list[Decimal] = []
    for item in items:
        original_discount = Decimal(str(item.discount_percent or 0))
        stashed.append(original_discount)
        inclusive = getattr(item, "unit_price_inclusive", None)
        if inclusive is None or Decimal(str(inclusive or 0)) == 0:
            # First save without dedicated field: treat current unit_price as inclusive input.
            inclusive = Decimal(item.unit_price)
            if hasattr(item, "unit_price_inclusive"):
                item.unit_price_inclusive = q2(inclusive)
        else:
            inclusive = Decimal(str(inclusive))
        exclusive_unit, taxable = extract_exclusive_from_inclusive_line(
            quantity=Decimal(item.quantity),
            unit_price_inclusive=inclusive,
            discount_percent=original_discount,
            gst_rate=Decimal(item.gst_rate or 0),
            cess_rate=Decimal(str(getattr(item, "cess_rate", 0) or 0)),
            cess_amount=Decimal(str(getattr(item, "cess_amount", 0) or 0)),
        )
        item.unit_price = exclusive_unit
        # Prefer extractor taxable for §3.3 paise fidelity when exclusive pipeline
        # would recompute from rounded unit_price (stash on item for optional use).
        item._inclusive_taxable = taxable  # noqa: SLF001
        # BB-000362: the discount was real (extracted from the inclusive gross)
        # even though discount_percent is zeroed for the exclusive pipeline —
        # stash the amount so document.discount_total still reflects it.
        line_gross_inclusive = q2(Decimal(item.quantity) * inclusive)
        item._inclusive_discount_amount = q2(  # noqa: SLF001
            line_gross_inclusive * original_discount / Decimal("100")
        )
        item.discount_percent = Decimal("0")
    return stashed


def apply_rcm_memo_after_tax(document, items) -> None:
    """
    Two-pass RCM: after tax was computed, copy liability into rcm_* memo,
    zero header+line tax, recompute grand_total as payable (taxable ± charges/discount).
    """
    if not getattr(document, "is_reverse_charge", False):
        return
    document.rcm_taxable = q2(Decimal(str(document.taxable_total or 0)))
    document.rcm_cgst = q2(Decimal(str(document.cgst_total or 0)))
    document.rcm_sgst = q2(Decimal(str(document.sgst_total or 0)))
    document.rcm_igst = q2(Decimal(str(document.igst_total or 0)))
    document.rcm_cess = q2(Decimal(str(getattr(document, "cess_total", 0) or 0)))
    document.cgst_total = Decimal("0.00")
    document.sgst_total = Decimal("0.00")
    document.igst_total = Decimal("0.00")
    if hasattr(document, "cess_total"):
        document.cess_total = Decimal("0.00")
    for item in items:
        item.cgst = Decimal("0.00")
        item.sgst = Decimal("0.00")
        item.igst = Decimal("0.00")
        if hasattr(item, "cess"):
            item.cess = Decimal("0.00")
        item.line_total = q2(Decimal(str(item.taxable_amount or 0)))

    charges = q2(Decimal(str(getattr(document, "additional_charges", 0) or 0)))
    discount = q2(Decimal(str(getattr(document, "invoice_discount", 0) or 0)))
    mode = getattr(document, "invoice_discount_mode", DISCOUNT_AFTER_TAX) or DISCOUNT_AFTER_TAX
    taxable = q2(Decimal(str(document.taxable_total or 0)))
    if mode == DISCOUNT_BEFORE_TAX:
        raw_total = taxable + charges
    else:
        # R1-019: reject an invoice-level discount larger than the payable value.
        if discount > taxable + charges:
            raise BusinessRuleError(
                f"Invoice discount {discount} exceeds the invoice value "
                f"{q2(taxable + charges)}."
            )
        raw_total = taxable + charges - discount
    if raw_total < 0:
        raw_total = Decimal("0")
    do_round = bool(getattr(document, "auto_round_off", True))
    if do_round:
        grand_total = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    else:
        grand_total = q2(raw_total)
    document.round_off = q2(grand_total - raw_total)
    document.grand_total = q2(grand_total)


def compute_document_totals(
    document,
    items,
    *,
    tax_enabled: bool,
    intra_state: bool,
    additional_charges: Decimal | None = None,
    invoice_discount: Decimal | None = None,
    auto_round_off: bool | None = None,
    invoice_discount_mode: str | None = None,
):
    """
    Mutates each item's computed fields and the document's totals.
    Does not save — callers persist inside their own transaction.

    invoice_discount_mode:
      AFTER_TAX  — subtract from grand total after GST (legacy default)
      BEFORE_TAX — allocate across line taxables proportionally, then compute GST

    If document.price_mode == INCLUSIVE, unit prices are treated as tax-inclusive
    and converted before the exclusive pipeline (discount already extracted).
    """
    price_mode = getattr(document, "price_mode", "EXCLUSIVE") or "EXCLUSIVE"
    stashed_discounts = apply_inclusive_prices_to_items(items, price_mode=price_mode)

    subtotal = Decimal("0")
    line_discount_total = Decimal("0")
    taxables: list[Decimal] = []

    for item in items:
        if price_mode == "INCLUSIVE" and hasattr(item, "_inclusive_taxable"):
            # §3.3: use extractor taxable so rounded exclusive unit does not drift paise.
            taxable = q2(getattr(item, "_inclusive_taxable"))
            gross = q2(Decimal(item.quantity) * Decimal(item.unit_price))
            # BB-000362: discount is already baked into `taxable` (extracted from
            # inclusive gross) — surface the stashed amount so discount_total
            # isn't silently reported as zero for inclusive-priced lines.
            discount = q2(Decimal(str(getattr(item, "_inclusive_discount_amount", 0) or 0)))
            # R1-018: document.subtotal must reflect the tax-inclusive gross the
            # customer sees (Σ qty×MRP), not the post-extraction exclusive gross —
            # otherwise Subtotal − Discount + Tax will not foot to Grand Total on
            # inclusive-priced documents. `_billing_gross` stays exclusive for the
            # PDF/serializer contract.
            _incl_unit = Decimal(str(getattr(item, "unit_price_inclusive", None) or 0))
            line_subtotal = (
                q2(Decimal(item.quantity) * _incl_unit) if _incl_unit > 0 else gross
            )
        else:
            gross = q2(Decimal(item.quantity) * Decimal(item.unit_price))
            discount = q2(gross * Decimal(item.discount_percent) / Decimal("100"))
            taxable = q2(gross - discount)
            line_subtotal = gross
        taxables.append(taxable)
        subtotal += line_subtotal
        line_discount_total += discount
        nature = (getattr(item, "supply_nature", None) or "TAXABLE").upper()
        if nature in ("NIL", "EXEMPT", "NON_GST"):
            if hasattr(item, "gst_rate"):
                item.gst_rate = Decimal("0")
            # R1-017: NIL / EXEMPT / NON_GST supplies never attract compensation
            # cess — clear any stray line cess so it cannot leak into cess_total.
            if hasattr(item, "cess_rate"):
                item.cess_rate = Decimal("0")
            if hasattr(item, "cess_amount"):
                item.cess_amount = Decimal("0")
            item._billing_rate = Decimal("0")  # noqa: SLF001
        else:
            item._billing_rate = Decimal(item.gst_rate) if tax_enabled else Decimal("0")  # noqa: SLF001
        item._billing_gross = gross  # noqa: SLF001
        item._billing_line_discount = discount  # noqa: SLF001

    charges = q2(
        Decimal(
            additional_charges
            if additional_charges is not None
            else getattr(document, "additional_charges", 0) or 0
        )
    )
    inv_discount = q2(
        Decimal(
            invoice_discount
            if invoice_discount is not None
            else getattr(document, "invoice_discount", 0) or 0
        )
    )
    mode = (
        invoice_discount_mode
        if invoice_discount_mode is not None
        else getattr(document, "invoice_discount_mode", DISCOUNT_AFTER_TAX) or DISCOUNT_AFTER_TAX
    )
    do_round = (
        auto_round_off
        if auto_round_off is not None
        else bool(getattr(document, "auto_round_off", True))
    )

    adjusted = list(taxables)
    if mode == DISCOUNT_BEFORE_TAX and inv_discount > 0 and items:
        taxable_sum = sum(taxables, Decimal("0"))
        if taxable_sum > 0:
            remaining = min(inv_discount, taxable_sum)
            # First pass: proportional share, clamped to each line's own taxable.
            allocated = Decimal("0")
            for i in range(len(adjusted)):
                share = q2(taxables[i] / taxable_sum * remaining)
                share = min(share, adjusted[i])
                adjusted[i] = q2(adjusted[i] - share)
                allocated += share
            # R1-020: any residual (rounding + lines clamped to zero) is spread
            # across the lines that still have headroom, instead of being dumped
            # on the last line and silently lost when that line clamps to zero.
            residual = q2(remaining - allocated)
            guard = 0
            while residual > Decimal("0") and guard < len(adjusted) + 2:
                guard += 1
                headroom = [i for i in range(len(adjusted)) if adjusted[i] > 0]
                if not headroom:
                    break
                per = q2(residual / Decimal(len(headroom)))
                if per <= 0:
                    for i in headroom:
                        if residual <= 0:
                            break
                        take = min(Decimal("0.01"), adjusted[i], residual)
                        adjusted[i] = q2(adjusted[i] - take)
                        residual = q2(residual - take)
                    break
                for i in headroom:
                    take = min(per, adjusted[i], residual)
                    adjusted[i] = q2(adjusted[i] - take)
                    residual = q2(residual - take)
        else:
            adjusted = [Decimal("0.00") for _ in adjusted]

    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")
    cess_total = Decimal("0")
    taxable_total = Decimal("0")

    for item, taxable in zip(items, adjusted):
        _apply_line_tax(
            item,
            taxable,
            getattr(item, "_billing_rate", Decimal("0")),
            tax_enabled=tax_enabled,
            intra_state=intra_state,
        )
        taxable_total += item.taxable_amount
        cgst_total += item.cgst
        sgst_total += item.sgst
        igst_total += item.igst
        cess_total += Decimal(str(getattr(item, "cess", 0) or 0))

    from core.services.charges import charge_line

    charge = charge_line(document, intra_state=intra_state) if tax_enabled else None
    if charge is not None:
        taxable_total += charge.taxable_amount
        cgst_total += charge.cgst
        sgst_total += charge.sgst
        igst_total += charge.igst
        charges_in_grand = Decimal("0")
    else:
        charges_in_grand = charges

    if mode == DISCOUNT_BEFORE_TAX:
        raw_total = taxable_total + cgst_total + sgst_total + igst_total + cess_total + charges_in_grand
    else:
        # R1-019: a data-entry error where the invoice-level discount exceeds the
        # invoice value must be rejected, not silently swallowed into a ₹0 total.
        pre_discount = (
            taxable_total + cgst_total + sgst_total + igst_total + cess_total + charges_in_grand
        )
        if inv_discount > pre_discount:
            raise BusinessRuleError(
                f"Invoice discount {q2(inv_discount)} exceeds the invoice value "
                f"{q2(pre_discount)}."
            )
        raw_total = pre_discount - inv_discount

    if raw_total < 0:
        raw_total = Decimal("0")
    if do_round:
        grand_total = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    else:
        grand_total = q2(raw_total)

    if hasattr(document, "additional_charges"):
        document.additional_charges = charges
    if hasattr(document, "invoice_discount"):
        document.invoice_discount = inv_discount
    if hasattr(document, "invoice_discount_mode"):
        document.invoice_discount_mode = mode

    document.subtotal = q2(subtotal)
    if mode == DISCOUNT_BEFORE_TAX:
        document.discount_total = q2(line_discount_total)
    else:
        document.discount_total = q2(line_discount_total + inv_discount)
    document.taxable_total = q2(taxable_total)
    document.cgst_total = q2(cgst_total)
    document.sgst_total = q2(sgst_total)
    document.igst_total = q2(igst_total)
    if hasattr(document, "cess_total"):
        document.cess_total = q2(cess_total)
    document.round_off = q2(grand_total - raw_total)
    document.grand_total = q2(grand_total)

    # Persist entered inclusive discounts (zeroed only for the exclusive tax pass).
    if stashed_discounts:
        for item, disc in zip(items, stashed_discounts):
            item.discount_percent = disc
            if hasattr(item, "_inclusive_taxable"):
                delattr(item, "_inclusive_taxable")
            if hasattr(item, "_inclusive_discount_amount"):
                delattr(item, "_inclusive_discount_amount")

    return document
