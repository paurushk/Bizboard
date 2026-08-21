"""NIC-style e-Invoice JSON builder (payload only — no IRP submission)."""

from __future__ import annotations

import re
from decimal import Decimal

from core.services.billing import extract_state_code, q2

from .models import SalesCreditNote, SalesDebitNote, SalesInvoice


def _seller_gstin(invoice) -> str:
    stamp = getattr(invoice, "company_gstin", None)
    stamped = (getattr(stamp, "gstin", None) or "").strip() if stamp is not None else ""
    return stamped or (invoice.company.gstin or "")


class EinvoiceValidationError(Exception):
    def __init__(self, errors: list[str] | str):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _state_code(gstin: str, state: str, label: str, errors: list[str]) -> str | None:
    code = extract_state_code(gstin) or extract_state_code(state)
    if not code:
        errors.append(f"{label} state code is required (set GSTIN or state with code).")
    return code


def _party_address(company) -> str:
    parts = [company.address or "", company.city or ""]
    return ", ".join(p for p in parts if p).strip()


def _pin(value: str | None, label: str, errors: list[str], *, required: bool = True) -> int | None:
    raw = (value or "").strip()
    if not raw:
        # Try extract 6-digit PIN from free text (addresses often include PIN).
        return None if not required else (_fail_pin(label, errors))
    if not re.fullmatch(r"\d{6}", raw):
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", raw)
        if m:
            return int(m.group(1))
        errors.append(f"{label} PIN code must be 6 digits.")
        return None
    return int(raw)


def _fail_pin(label: str, errors: list[str]) -> None:
    errors.append(f"{label} PIN code is required (6 digits).")
    return None


def _extract_pin_from_text(text: str | None) -> str:
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", text or "")
    return m.group(1) if m else ""


_EXPORT_SEZ_SUPPLY = frozenset({"SEZWP", "SEZWOP", "EXPWP", "EXPWOP", "DEXP"})


def _is_export_or_sez_supply(invoice) -> bool:
    supply = (getattr(invoice, "supply_type", None) or "").strip().upper()
    return supply in _EXPORT_SEZ_SUPPLY


def validate_einvoice_readiness(invoice: SalesInvoice) -> list[str]:
    errors: list[str] = []
    if invoice.invoice_type != SalesInvoice.InvoiceType.GST:
        errors.append("Only GST invoices support e-Invoice.")
    if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
        errors.append("Invoice must be completed before preparing e-Invoice.")
    if not invoice.number:
        errors.append("Invoice number is required.")

    company = invoice.company
    customer = invoice.customer
    buyer_gstin = (getattr(invoice, "filing_party_gstin", None) or "").strip() or (customer.gstin or "")
    seller_gstin = _seller_gstin(invoice)
    stamp = getattr(invoice, "company_gstin", None)
    is_export_sez = _is_export_or_sez_supply(invoice)

    if not seller_gstin:
        errors.append("Company GSTIN is required.")
    seller_address = (
        (getattr(stamp, "address", None) or "").strip()
        if stamp is not None
        else ""
    ) or _party_address(company)
    if not seller_address:
        errors.append("Company address is required.")
    seller_state = (
        (getattr(stamp, "state", None) or "").strip()
        if stamp is not None
        else ""
    ) or company.state
    _state_code(seller_gstin, seller_state, "Company", errors)
    seller_pin_src = (
        (getattr(stamp, "pincode", None) or "").strip()
        if stamp is not None
        else ""
    ) or getattr(company, "pincode", None) or ""
    _pin(seller_pin_src, "Company", errors)

    # Export/SEZ: buyer GSTIN not required (URP + POS 96 at payload build).
    if not buyer_gstin and not is_export_sez:
        errors.append("Customer GSTIN is required.")
    if not (customer.billing_address or "").strip():
        errors.append("Customer billing address is required.")
    buyer_state = (getattr(invoice, "filing_place_of_supply", None) or "").strip() or customer.state
    if is_export_sez:
        # Unresolved free-text → 96 at build; only validate when a code is resolvable.
        if buyer_gstin or extract_state_code(buyer_state):
            _state_code(buyer_gstin, buyer_state, "Customer", errors)
    else:
        _state_code(buyer_gstin, buyer_state, "Customer", errors)
    buyer_pin_src = (
        getattr(customer, "pincode", None)
        or getattr(customer, "billing_pincode", None)
        or _extract_pin_from_text(customer.billing_address)
        or ""
    )
    # Export/SEZ: PIN optional (NIC common practice 999999 for URP overseas).
    _pin(str(buyer_pin_src), "Customer", errors, required=not is_export_sez)

    items = list(invoice.items.all())
    if not items:
        errors.append("Invoice must have at least one line item.")
    for idx, item in enumerate(items, start=1):
        if not (item.hsn_code or "").strip():
            errors.append(f"Line {idx}: HSN code is required.")

    return errors


def _fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y")


def _num(value: Decimal | int | float | str | None) -> str:
    """NIC-safe decimal string (no float)."""
    return f"{q2(Decimal(str(value or 0))):.2f}"


def build_einvoice_payload(invoice: SalesInvoice) -> dict:
    errors = validate_einvoice_readiness(invoice)
    if errors:
        raise EinvoiceValidationError(errors)

    company = invoice.company
    customer = invoice.customer
    # Detect SEZ/export before hard buyer GSTIN requirement.
    sez_flag = (getattr(invoice, "supply_type", None) or getattr(customer, "taxpayer_type", None) or "")
    sez_flag = str(sez_flag).strip().upper()
    is_export_sez = sez_flag in _EXPORT_SEZ_SUPPLY

    buyer_gstin = (getattr(invoice, "filing_party_gstin", None) or "").strip() or (customer.gstin or "")
    buyer_stcd = (
        (getattr(invoice, "filing_place_of_supply", None) or "").strip()
        or extract_state_code(buyer_gstin)
        or extract_state_code(customer.state)
        or ""
    )
    if is_export_sez and not buyer_gstin:
        buyer_gstin = "URP"
        buyer_stcd = "96"
    elif is_export_sez and not extract_state_code(buyer_stcd) and not extract_state_code(buyer_gstin):
        buyer_stcd = "96"
    elif not is_export_sez and not buyer_gstin.strip():
        # BB-000324: SupTyp B2B requires a buyer GSTIN — not for export/SEZ URP.
        raise EinvoiceValidationError(
            ["Customer GSTIN is required for e-Invoice (unregistered/B2C buyers are not supported)."]
        )

    seller_gstin = _seller_gstin(invoice)
    stamp = getattr(invoice, "company_gstin", None)
    seller_state = (
        (getattr(stamp, "state", None) or "").strip() if stamp is not None else ""
    ) or company.state
    seller_stcd = extract_state_code(seller_gstin) or extract_state_code(seller_state) or ""
    if stamp is not None:
        # Prefer stamp fields; fall back to company HO for blank address/PIN/city.
        # GSTIN/state still come from the stamp (seller_gstin / seller_state above).
        seller_pin_src = (getattr(stamp, "pincode", None) or "").strip() or (company.pincode or "").strip()
        seller_addr = (getattr(stamp, "address", None) or "").strip() or _party_address(company)
        seller_city = (
            (getattr(stamp, "city", None) or "").strip()
            or (company.city or "").strip()
            or (company.state or "")
        )
        if not seller_state:
            raise EinvoiceValidationError(
                ["CompanyGstin stamp state is required when a branch GSTIN stamp is set."]
            )
        if not seller_addr or not seller_pin_src:
            raise EinvoiceValidationError(
                ["Seller address and pincode are required (set on CompanyGstin stamp or company HO)."]
            )
    else:
        seller_pin_src = (company.pincode or "").strip()
        seller_addr = _party_address(company)
        seller_city = company.city or company.state or ""
    seller_pin_m = re.fullmatch(r"\d{6}", seller_pin_src)
    if not seller_pin_m:
        extracted = _extract_pin_from_text(seller_addr or seller_pin_src)
        if not extracted or extracted == "0":
            raise EinvoiceValidationError(["Seller pincode must be a valid 6-digit PIN."])
        seller_pin = int(extracted)
    else:
        seller_pin = int(seller_pin_m.group(0))
    buyer_pin_raw = (
        getattr(customer, "pincode", None)
        or getattr(customer, "billing_pincode", None)
        or _extract_pin_from_text(customer.billing_address)
        or ""
    )
    if re.fullmatch(r"\d{6}", str(buyer_pin_raw).strip()):
        buyer_pin = int(str(buyer_pin_raw).strip())
    else:
        extracted_b = _extract_pin_from_text(str(buyer_pin_raw))
        if extracted_b and extracted_b != "0":
            buyer_pin = int(extracted_b)
        elif is_export_sez:
            buyer_pin = 999999  # NIC common practice for URP overseas exports
        else:
            raise EinvoiceValidationError("Buyer pincode must be a valid 6-digit PIN.")

    item_list = []
    for idx, item in enumerate(invoice.items.select_related("product").all(), start=1):
        qty = Decimal(str(item.quantity or 0))
        unit_price = Decimal(str(item.unit_price or 0))
        discount_pct = Decimal(str(item.discount_percent or 0))
        gross = q2(qty * unit_price)
        discount = q2(gross * discount_pct / Decimal("100"))
        ass_amt = Decimal(str(item.taxable_amount or 0))
        product = item.product
        is_service = bool(getattr(product, "is_service", False) or getattr(product, "product_type", "") == "SERVICE")
        uqc = (item.uqc_code or "").strip() or "NOS"
        item_list.append({
            "SlNo": str(idx),
            "PrdDesc": item.description or product.name,
            "IsServc": "Y" if is_service else "N",
            "HsnCd": item.hsn_code,
            "Qty": _num(qty),
            "Unit": uqc,
            "UnitPrice": _num(unit_price),
            "TotAmt": _num(gross),
            "Discount": _num(discount),
            "AssAmt": _num(ass_amt),
            "GstRt": _num(item.gst_rate),
            "CgstAmt": _num(item.cgst),
            "SgstAmt": _num(item.sgst),
            "IgstAmt": _num(item.igst),
            "CesRt": _num(getattr(item, "cess_rate", 0)),
            "CesAmt": _num(getattr(item, "cess", 0)),
            "TotItemVal": _num(item.line_total),
        })

    # BB-000287: derive TranDtls from invoice; default B2B/N for normal B2B only.
    is_rcm = bool(getattr(invoice, "is_reverse_charge", False))
    if is_rcm:
        sup_typ = "B2B"
        reg_rev = "Y"
    elif is_export_sez:
        sup_typ = sez_flag
        reg_rev = "N"
    else:
        sup_typ = "B2B"
        reg_rev = "N"

    if is_export_sez:
        buyer_stcd = buyer_stcd if extract_state_code(buyer_stcd) else "96"
        buyer_pos = "96"
    else:
        buyer_pos = buyer_stcd

    # BB-000277: AssVal is already net of BEFORE_TAX invoice discount — only residual
    # AFTER_TAX cash discount belongs in ValDtls.Discount (preserves TotInvVal identity).
    discount_mode = getattr(invoice, "invoice_discount_mode", SalesInvoice.DiscountMode.AFTER_TAX)
    val_discount = (
        Decimal(str(invoice.invoice_discount or 0))
        if discount_mode == SalesInvoice.DiscountMode.AFTER_TAX
        else Decimal("0")
    )

    return {
        "Version": "1.1",
        "TranDtls": {
            "TaxSch": "GST",
            "SupTyp": sup_typ,
            "RegRev": reg_rev,
            "EcmGstin": (getattr(invoice, "ecommerce_operator_gstin", None) or "").strip() or None,
            "IgstOnIntra": "N",
        },
        "DocDtls": {
            "Typ": "INV",
            "No": invoice.number,
            "Dt": _fmt_date(invoice.invoice_date),
        },
        "SellerDtls": {
            "Gstin": seller_gstin,
            "LglNm": (
                (getattr(stamp, "legal_name", None) or "").strip()
                if stamp is not None
                else ""
            ) or company.legal_name or company.name,
            "TrdNm": company.name,
            "Addr1": seller_addr,
            "Loc": seller_city,
            "Pin": seller_pin,
            "Stcd": seller_stcd,
        },
        "BuyerDtls": {
            "Gstin": buyer_gstin,
            "LglNm": customer.name,
            "TrdNm": customer.name,
            "Addr1": customer.billing_address.strip(),
            "Loc": customer.state or "",
            "Pin": buyer_pin,
            "Stcd": buyer_stcd,
            "Pos": buyer_pos,
        },
        "ItemList": item_list,
        "ValDtls": {
            "AssVal": _num(invoice.taxable_total),
            "CgstVal": _num(invoice.cgst_total),
            "SgstVal": _num(invoice.sgst_total),
            "IgstVal": _num(invoice.igst_total),
            "CesVal": _num(getattr(invoice, "cess_total", 0) or 0),
            "StCesVal": _num(0),
            "Discount": _num(val_discount),
            "OthChrg": _num(invoice.additional_charges),
            "RndOffAmt": _num(invoice.round_off),
            "TotInvVal": _num(invoice.grand_total),
        },
    }


def build_einvoice_payload_from_note(note) -> dict:
    """BB-000647: CRN/DBN payload with PrecDocDtls pointing at the source invoice."""
    inv = note.sales_invoice
    payload = build_einvoice_payload(inv)
    if isinstance(note, SalesDebitNote):
        typ = "DBN"
    else:
        typ = "CRN"
    payload["DocDtls"] = {
        "Typ": typ,
        "No": note.number,
        "Dt": _fmt_date(note.note_date),
    }
    payload["PrecDocDtls"] = [{
        "InvNo": inv.number or "",
        "InvDt": _fmt_date(inv.invoice_date),
        "Irn": inv.irn or "",
    }]
    payload["ValDtls"] = {
        "AssVal": _num(note.taxable_total),
        "CgstVal": _num(note.cgst_total),
        "SgstVal": _num(note.sgst_total),
        "IgstVal": _num(note.igst_total),
        "CesVal": _num(getattr(note, "cess_total", 0) or 0),
        "StCesVal": _num(0),
        "Discount": _num(getattr(note, "invoice_discount", 0) or 0),
        "OthChrg": _num(getattr(note, "additional_charges", 0) or 0),
        "RndOffAmt": _num(note.round_off),
        "TotInvVal": _num(note.grand_total),
    }
    item_list = []
    for idx, item in enumerate(note.items.select_related("product").all(), start=1):
        qty = Decimal(str(item.quantity or 0))
        unit_price = Decimal(str(item.unit_price or 0))
        discount_pct = Decimal(str(item.discount_percent or 0))
        gross = q2(qty * unit_price)
        discount = q2(gross * discount_pct / Decimal("100"))
        product = item.product
        is_service = bool(getattr(product, "is_service", False) or getattr(product, "product_type", "") == "SERVICE")
        item_list.append({
            "SlNo": str(idx),
            "PrdDesc": item.description or product.name,
            "IsServc": "Y" if is_service else "N",
            "HsnCd": item.hsn_code,
            "Qty": _num(qty),
            "Unit": (item.uqc_code or "").strip() or "NOS",
            "UnitPrice": _num(unit_price),
            "TotAmt": _num(gross),
            "Discount": _num(discount),
            "AssAmt": _num(item.taxable_amount),
            "GstRt": _num(item.gst_rate),
            "CgstAmt": _num(item.cgst),
            "SgstAmt": _num(item.sgst),
            "IgstAmt": _num(item.igst),
            "CesRt": _num(getattr(item, "cess_rate", 0)),
            "CesAmt": _num(getattr(item, "cess", 0)),
            "TotItemVal": _num(item.line_total),
        })
    payload["ItemList"] = item_list
    return payload
