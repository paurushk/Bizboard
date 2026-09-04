"""e-Way bill JSON builder (payload only — no NIC submission)."""

from __future__ import annotations

import re
from decimal import Decimal

from core.exceptions import BusinessRuleError
from core.services.billing import extract_state_code, q2

from .models import DeliveryChallan, SalesInvoice


class EwayValidationError(Exception):
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


def _fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y")


def _num(value: Decimal | int | float | str | None) -> str:
    """NIC-safe decimal string (no float) — parity with einvoice_payload."""
    return f"{q2(Decimal(str(value or 0))):.2f}"


_VEHICLE_RE = re.compile(
    r"^(?:[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}|\d{2}BH[0-9]{4}[A-Z]{1,2})$",
    re.I,
)
_TRANSPORTER_ID_RE = re.compile(
    r"^(?:[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]|\d{12})$",
    re.I,
)


def validate_eway_transport(
    *,
    vehicle_number: str = "",
    distance_km=None,
    transporter_id: str = "",
) -> list[str]:
    """Wave 16D: NIC-strict vehicle / distance / transporter id checks."""
    errors: list[str] = []
    v = (vehicle_number or "").replace(" ", "").upper()
    if v and not _VEHICLE_RE.match(v):
        errors.append(
            "vehicleNo must match Indian registration pattern "
            "(e.g. MH12AB1234 or 22BH1234AA)."
        )
    tid = (transporter_id or "").replace(" ", "").upper()
    if tid and not _TRANSPORTER_ID_RE.match(tid):
        errors.append("transporter_id must be a 15-char GSTIN or 12-digit TRANSIN.")
    if distance_km is None:
        errors.append("transport_distance_km is required for e-Way Bill.")
    else:
        try:
            d = int(distance_km)
            if d < 1 or d > 4000:
                errors.append("transDistance must be between 1 and 4000 km.")
        except (TypeError, ValueError):
            errors.append("transDistance must be an integer kilometre value.")
    return errors


def _extract_pin(text: str | None) -> str:
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", text or "")
    return m.group(1) if m else ""


def _from_pincode(company, stamp=None) -> int:
    raw = ((getattr(stamp, "pincode", None) or "").strip() if stamp is not None else "") or (
        getattr(company, "pincode", None) or ""
    ).strip()
    if re.fullmatch(r"\d{6}", raw):
        return int(raw)
    extracted = _extract_pin(
        ((getattr(stamp, "address", None) or "").strip() if stamp is not None else "") or _party_address(company)
    )
    if extracted:
        return int(extracted)
    raise BusinessRuleError("Company pincode is required (6 digits) for e-Way Bill.")


def _buyer_pincode(customer) -> int:
    """Require a real 6-digit buyer PIN (never invent 0)."""
    raw = (
        getattr(customer, "pincode", None)
        or getattr(customer, "billing_pincode", None)
        or ""
    )
    raw = str(raw).strip()
    if re.fullmatch(r"\d{6}", raw):
        return int(raw)
    for text in (
        customer.shipping_address or "",
        customer.billing_address or "",
    ):
        pin = _extract_pin(text)
        if pin:
            return int(pin)
    raise BusinessRuleError("Customer pincode is required (6 digits) for e-Way Bill.")


def _validate_company_party(company, errors: list[str], *, seller_gstin: str = "", stamp=None) -> str | None:
    gstin = (seller_gstin or company.gstin or "").strip()
    if stamp is not None:
        state = (getattr(stamp, "state", None) or "").strip()
        address = (getattr(stamp, "address", None) or "").strip()
        pin = (getattr(stamp, "pincode", None) or "").strip()
        if not address:
            errors.append("CompanyGstin stamp address is required (HO fallback disabled).")
        if not pin:
            errors.append("CompanyGstin stamp pincode is required (HO fallback disabled).")
        if not state:
            errors.append("CompanyGstin stamp state is required (HO fallback disabled).")
    else:
        state = company.state
        address = _party_address(company)
        pin = (company.pincode or "").strip()
    if not gstin:
        errors.append("Company GSTIN is required.")
    if not address:
        errors.append("Company address is required.")
    if not pin:
        errors.append("Company pincode is required.")
    return _state_code(gstin, state, "Company", errors)


def _validate_customer_party(customer, errors: list[str]) -> str | None:
    # BB-000430: B2C/URP allowed without GSTIN; GSTIN required only when present path is B2B.
    if customer.gstin:
        return _state_code(customer.gstin, customer.state, "Customer", errors)
    if not (customer.billing_address or customer.shipping_address or "").strip():
        errors.append("Customer address is required.")
    try:
        _buyer_pincode(customer)
    except BusinessRuleError as exc:
        errors.append(str(exc))
    # URP — use state code from customer.state when available.
    return _state_code("", customer.state, "Customer", errors)


def _line_hsn(item) -> str:
    return (
        (getattr(item, "hsn_code", "") or "").strip()
        or (getattr(getattr(item, "product", None), "hsn_code", "") or "").strip()
    )


def _line_uqc(item) -> str:
    return (getattr(item, "uqc_code", None) or "").strip() or "NOS"


def _build_item_list(items, *, require_hsn: bool, errors: list[str]) -> list[dict]:
    item_list = []
    for idx, item in enumerate(items, start=1):
        hsn = _line_hsn(item)
        if require_hsn and not hsn:
            product_name = getattr(getattr(item, "product", None), "name", f"Line {idx}")
            errors.append(f"Line {idx} ({product_name}): HSN code is required.")
        gst_rate = Decimal(str(item.gst_rate or 0))
        half_rate = q2(gst_rate / 2) if item.cgst or item.sgst else Decimal("0")
        item_list.append({
            "itemNo": idx,
            "productName": item.description or item.product.name,
            "productDesc": item.description or item.product.name,
            "hsnCode": hsn,
            "quantity": _num(item.quantity),
            "qtyUnit": _line_uqc(item),
            "taxableAmount": _num(item.taxable_amount),
            "cgstRate": _num(half_rate) if item.cgst else _num(0),
            "sgstRate": _num(half_rate) if item.sgst else _num(0),
            "igstRate": _num(gst_rate) if item.igst else _num(0),
            "cgstAmount": _num(item.cgst),
            "sgstAmount": _num(item.sgst),
            "igstAmount": _num(item.igst),
        })
    return item_list


def validate_eway_from_invoice(invoice: SalesInvoice) -> list[str]:
    errors: list[str] = []
    if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
        errors.append("Invoice must be completed before preparing e-Way bill.")
    if not invoice.number:
        errors.append("Invoice number is required.")
    stamp = getattr(invoice, "company_gstin", None)
    seller_gstin = ((getattr(stamp, "gstin", None) or "").strip() if stamp is not None else "") or (
        invoice.company.gstin or ""
    )
    _validate_company_party(invoice.company, errors, seller_gstin=seller_gstin, stamp=stamp)
    _validate_customer_party(invoice.customer, errors)
    items = list(invoice.items.select_related("product").all())
    if not items:
        errors.append("Invoice must have at least one line item.")
    _build_item_list(items, require_hsn=True, errors=errors)
    errors.extend(
        validate_eway_transport(
            vehicle_number=getattr(invoice, "vehicle_number", "") or "",
            distance_km=getattr(invoice, "transport_distance_km", None),
            transporter_id=getattr(invoice, "transporter_id", "") or "",
        )
    )
    return errors


def validate_eway_from_challan(challan: DeliveryChallan) -> list[str]:
    errors: list[str] = []
    if challan.status != DeliveryChallan.Status.COMPLETED:
        errors.append("Challan must be completed before preparing e-Way bill.")
    if not challan.number:
        errors.append("Challan number is required.")
    inv = getattr(challan, "converted_invoice", None)
    stamp = getattr(inv, "company_gstin", None) if inv is not None else None
    seller_gstin = ((getattr(stamp, "gstin", None) or "").strip() if stamp is not None else "") or (
        challan.company.gstin or ""
    )
    _validate_company_party(challan.company, errors, seller_gstin=seller_gstin, stamp=stamp)
    _validate_customer_party(challan.customer, errors)
    items = list(challan.items.select_related("product").all())
    if not items:
        errors.append("Challan must have at least one line item.")
    _build_item_list(items, require_hsn=True, errors=errors)
    errors.extend(
        validate_eway_transport(
            vehicle_number=challan.vehicle_number or "",
            distance_km=getattr(challan, "transport_distance_km", None),
            transporter_id=getattr(challan, "transporter_id", "") or "",
        )
    )
    return errors


def build_eway_payload_from_invoice(
    invoice: SalesInvoice,
    *,
    vehicle_number: str = "",
    transporter_name: str = "",
    challan: DeliveryChallan | None = None,
) -> dict:
    errors = validate_eway_from_invoice(invoice)
    if errors:
        raise EwayValidationError(errors)

    if challan is not None:
        vehicle_number = vehicle_number or challan.vehicle_number or ""
        transporter_name = transporter_name or challan.transporter_name or ""

    company = invoice.company
    customer = invoice.customer
    seller_gstin = ""
    stamp = getattr(invoice, "company_gstin", None)
    if stamp is not None:
        seller_gstin = (getattr(stamp, "gstin", None) or "").strip()
    seller_gstin = seller_gstin or (company.gstin or "")
    seller_state = ((getattr(stamp, "state", None) or "").strip() if stamp is not None else "") or company.state
    from_stcd = extract_state_code(seller_gstin) or extract_state_code(seller_state) or ""
    to_stcd = extract_state_code(customer.gstin) or extract_state_code(customer.state) or ""
    items = list(invoice.items.select_related("product").all())
    distance = getattr(invoice, "transport_distance_km", None)
    if distance is None:
        raise EwayValidationError(["transport_distance_km is required for e-Way Bill."])
    trans_distance = str(int(distance))
    to_pin = _buyer_pincode(customer)
    from_pin = _from_pincode(company, stamp)
    sub_supply = str(invoice.sub_supply_type or "1")
    trans_mode = str(invoice.trans_mode or "1")

    return {
        "supplyType": "O",
        "subSupplyType": sub_supply,
        "docType": "INV",
        "docNo": invoice.number,
        "docDate": _fmt_date(invoice.invoice_date),
        "fromGstin": seller_gstin,
        "fromTrdName": company.name,
        "fromAddr1": (
            (getattr(stamp, "address", None) or "").strip()
            if stamp is not None
            else _party_address(company)
        ),
        "fromPlace": company.city or company.state or "",
        "fromPincode": from_pin,
        "fromStateCode": int(from_stcd) if from_stcd.isdigit() else 0,
        "toGstin": (customer.gstin or "").strip() or "URP",
        "toTrdName": customer.name,
        "toAddr1": (customer.shipping_address or customer.billing_address or "").strip(),
        "toPlace": customer.state or "",
        "toPincode": to_pin,
        "toStateCode": int(to_stcd) if to_stcd.isdigit() else 0,
        "totalValue": _num(invoice.taxable_total),
        "cgstValue": _num(invoice.cgst_total),
        "sgstValue": _num(invoice.sgst_total),
        "igstValue": _num(invoice.igst_total),
        "totInvValue": _num(invoice.grand_total),
        "transMode": trans_mode,
        "transDistance": trans_distance,
        "transporterName": transporter_name,
        "transporterId": (getattr(invoice, "transporter_id", "") or "").replace(" ", "").upper(),
        "vehicleNo": (vehicle_number or "").replace(" ", "").upper(),  # B2-013
        "itemList": _build_item_list(items, require_hsn=False, errors=[]),
    }


def build_eway_payload_from_challan(challan: DeliveryChallan) -> dict:
    errors = validate_eway_from_challan(challan)
    if errors:
        raise EwayValidationError(errors)

    company = challan.company
    customer = challan.customer
    seller_gstin = company.gstin or ""
    inv = getattr(challan, "converted_invoice", None)
    stamp = getattr(inv, "company_gstin", None) if inv is not None else None
    if stamp is not None:
        seller_gstin = (getattr(stamp, "gstin", None) or seller_gstin).strip()
    seller_state = ((getattr(stamp, "state", None) or "").strip() if stamp is not None else "") or company.state
    from_stcd = extract_state_code(seller_gstin) or extract_state_code(seller_state) or ""
    to_stcd = extract_state_code(customer.gstin) or extract_state_code(customer.state) or ""
    items = list(challan.items.select_related("product").all())
    to_pin = _buyer_pincode(customer)
    from_pin = _from_pincode(company, stamp)
    distance = getattr(challan, "transport_distance_km", None)
    if distance is None:
        raise EwayValidationError(["transport_distance_km is required for e-Way Bill."])
    sub_supply = str(challan.sub_supply_type or "8")
    trans_mode = str(challan.trans_mode or "1")

    return {
        "supplyType": "O",
        "subSupplyType": sub_supply,
        "docType": "CHL",
        "docNo": challan.number,
        "docDate": _fmt_date(challan.challan_date),
        "fromGstin": seller_gstin,
        "fromTrdName": company.name,
        "fromAddr1": (
            (getattr(stamp, "address", None) or "").strip()
            if stamp is not None
            else _party_address(company)
        ),
        "fromPlace": company.city or company.state or "",
        "fromPincode": from_pin,
        "fromStateCode": int(from_stcd) if from_stcd.isdigit() else 0,
        "toGstin": (customer.gstin or "").strip() or "URP",
        "toTrdName": customer.name,
        "toAddr1": (customer.shipping_address or customer.billing_address or "").strip(),
        "toPlace": customer.state or "",
        "toPincode": to_pin,
        "toStateCode": int(to_stcd) if to_stcd.isdigit() else 0,
        "totalValue": _num(challan.taxable_total),
        "cgstValue": _num(challan.cgst_total),
        "sgstValue": _num(challan.sgst_total),
        "igstValue": _num(challan.igst_total),
        "totInvValue": _num(challan.grand_total),
        "transMode": trans_mode,
        "transDistance": str(int(distance)),
        "transporterName": challan.transporter_name or "",
        "transporterId": (challan.transporter_id or "").replace(" ", "").upper(),
        "vehicleNo": (challan.vehicle_number or "").replace(" ", "").upper(),  # B2-013
        "itemList": _build_item_list(items, require_hsn=False, errors=[]),
    }
