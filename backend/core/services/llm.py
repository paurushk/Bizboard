"""Configurable LLM client for purchase-bill / rate-list vision extraction."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from django.conf import settings

from core.exceptions import BusinessRuleError
from core.services.bill_images import views_for_si_range

logger = logging.getLogger("imports.extract")

EXTRACT_PROMPT = """Extract purchase bill / tax invoice / rate-list line items from the attached document image(s).
Return ONLY valid JSON (no markdown) with this exact shape:
{
  "supplier_name": "",
  "supplier_gstin": "",
  "buyer_name": "",
  "buyer_gstin": "",
  "bill_number": "",
  "bill_date": "",
  "confidence": "0.85",
  "printed_line_count": "",
  "column_headers": ["the", "literal", "header", "row", "left-to-right"],
  "lines": [
    {
      "si": "",
      "name": "",
      "sku": "",
      "hsn_code": "",
      "quantity": "",
      "unit_price": "0",
      "gst_rate": "",
      "mrp": "0",
      "printed_gross_amt": "",
      "raw_columns": {},
      "confidence": "0.85"
    }
  ]
}

This must work for ANY Indian GST tax-invoice layout, not one vendor. Copy columns as printed;
do not invent a billed quantity by combining columns (that is done downstream against printed amounts).

Canonical fields:
- si ← Sl / SI / S.No when the table is numbered (digits only). Omit if unnumbered.
- name ← Item Description / Particulars / Product Name (required).
- sku ← Item Code / Product Code / Material Code / PCode when present.
- hsn_code ← HSN / HSN/SAC (digits only).
- quantity ← the column that is already a billed quantity as printed: Qty, Quantity, Nos, Pcs, Pcs
  billed, Weight, Kg, Ltr. If several qty-like columns exist (Cases + Pcs, Box + Pack, Strips +
  Pcs), put the "loose / inner" count here (0 is valid — do not skip the row) and put the others
  in raw_columns. NEVER multiply or add columns yourself.
  If the table has Cs / Cases / Cartons / Box, raw_columns must include that key on EVERY row
  (use "0" when the cell is 0 — do not omit it). Handwritten ticks on Cs/Pcs are still the
  printed digit underneath; do not copy Cs/Pcs/UPC from a neighbouring row.
- unit_price ← Rate / Price / Pc Price / Basic Rate (per billed unit, BEFORE tax).
  If Rate is missing but a line amount and quantity are readable: unit_price = amount ÷ quantity.
  NEVER use Gross/Net/Tax/Scheme/Discount amounts as unit_price.
- mrp ← MRP when present.
- gst_rate ← total GST % (CGST%+SGST%, or IGST%, or GST%). Examples: 2.5+2.5 → "5"; 9+9 → "18".
- printed_gross_amt ← the line amount that should equal billed-qty × unit_price when no line
  discount applies: Gross Amt, Amount, Value, or Taxable Amt — read verbatim.
- raw_columns ← EVERY other quantity / pack-size column on that row, keyed by the printed header
  (lower-case). Examples of different vendors:
    {"cs": "5", "upc": "24"}
    {"boxes": "2", "pack": "12"}
    {"strips": "10"}
    {"doz": "4"}
  Do NOT put money columns here (rate, mrp, amount, tax, discount, gst).
- column_headers ← the literal header row, left to right, un-normalized.
- printed_line_count ← last numbered SI/Sl on the item table (not how many rows you emitted).
  If the table is unnumbered, count the product rows visible on the bill.
- buyer_* ← Bill-To party; supplier_* ← seller / from party.

Rules:
- Extract EVERY product row. Dense invoices often have 30–80+ lines. Do not stop after 10 or 20.
- If output space is tight, close valid JSON, set printed_line_count correctly, and emit as many
  lines as you can in order — a follow-up call will fetch the rest.
- Numeric fields are plain numeric strings (no ₹, no commas). Printed 0 stays "0"; unread stays "".
- gst_rate must be one of 0, 0.25, 3, 5, 12, 18, 28 when known — never invent 18.
- Skip tax-summary bands, grand totals, margin rows, and header-only rows.
- bill_number ← Invoice/Bill No; bill_date as YYYY-MM-DD when possible.
- Photos may be tilted, stamped, or handwritten-over — still extract readable print; lower confidence when unsure.
- Unknown fields: "".
- confidence: 0.0–1.0 overall; per-line confidence optional.
"""

# Dense GST invoices (30–80 lines) need a large completion budget; 4096 truncates
# mid-JSON and json_object mode then closes early at ~20 rows.
EXTRACT_MAX_TOKENS = 16384
EXTRACT_TIMEOUT_SECONDS = 90.0
# gpt-4o-mini routinely emits ~20 lines and reports printed_line_count=20 even
# when SI 21–30 are visible. Pull the table in SI windows instead.
EXTRACT_CHUNK_SIZE = 15
MAX_EXTRACT_CHUNKS = 4
MIN_LINES_TO_PROBE_MORE = 8

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    # DeepSeek chat has no vision — use a vision-capable model when provider=deepseek.
    "deepseek": "deepseek-vl2",
    "claude": "claude-sonnet-4-20250514",
}

# Bill photos are a different job than chat/insights — mini cannot read a
# 30×19 DMS table on a WhatsApp JPEG. Override with LLM_BILL_MODEL.
DEFAULT_BILL_MODELS = {
    "openai": "gpt-4o",
    "deepseek": "deepseek-vl2",
    "claude": "claude-sonnet-4-20250514",
}


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        return "image/webp"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    return "image/png"


def _provider() -> str:
    return (getattr(settings, "LLM_PROVIDER", None) or "openai").strip().lower()


def _model_for(provider: str) -> str:
    override = (getattr(settings, "LLM_MODEL", None) or "").strip()
    if override:
        return override
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["openai"])


def _bill_model_for(provider: str) -> str:
    override = (getattr(settings, "LLM_BILL_MODEL", None) or "").strip()
    if override:
        return override
    return DEFAULT_BILL_MODELS.get(provider, DEFAULT_BILL_MODELS["openai"])


def _parse_json_content(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise BusinessRuleError("LLM returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise BusinessRuleError("LLM response was not valid JSON.")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise BusinessRuleError("LLM response was not valid JSON.") from exc


def _coerce_gst_rate(raw: Any) -> str:
    """Normalize GST strings including CGST+SGST / IGST forms to an allowed slab."""
    if raw in (None, ""):
        return ""
    text = str(raw).strip().replace(",", "")
    if not text:
        return ""
    allowed = {"0", "0.25", "3", "5", "12", "18", "28"}
    upper = text.upper()
    parts = re.findall(r"(\d+(?:\.\d+)?)", text)
    total: float | None = None
    try:
        if "IGST" in upper and parts:
            total = float(parts[0])
        elif len(parts) >= 2 and ("+" in text or "CGST" in upper or "SGST" in upper):
            total = float(parts[0]) + float(parts[1])
        elif len(parts) == 1:
            total = float(parts[0])
    except (TypeError, ValueError):
        total = None
    if total is None:
        return ""
    for slab in allowed:
        if abs(total - float(slab)) < 0.05:
            return slab
    return ""


def _normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    lines_in = raw.get("lines") or []
    if not isinstance(lines_in, list):
        raise BusinessRuleError("LLM JSON must include a lines array.")
    lines = []
    for item in lines_in:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        qty_raw = item.get("quantity")
        qty = "" if qty_raw in (None, "") else str(qty_raw).strip().replace(",", "")
        gst_rate = _coerce_gst_rate(
            item.get("gst_rate", item.get("gstRate", item.get("gst")))
        )
        unit_raw = item.get("unit_price", item.get("unitPrice", item.get("rate", item.get("pc_price"))))
        unit_price = "" if unit_raw in (None, "") else str(unit_raw).strip().replace(",", "")
        if not unit_price:
            unit_price = "0"
        mrp_raw = item.get("mrp")
        mrp = "" if mrp_raw in (None, "") else str(mrp_raw).strip().replace(",", "")
        if not mrp:
            mrp = "0"
        line_conf = item.get("confidence")
        if line_conf in (None, ""):
            line_conf = raw.get("confidence")
        unread = (not qty) or (not gst_rate)
        try:
            confidence = float(line_conf) if line_conf not in (None, "") else None
        except (TypeError, ValueError):
            confidence = None

        def _raw_num(*keys):
            for key in keys:
                value = item.get(key)
                if value not in (None, ""):
                    return str(value).strip().replace(",", "")
            return ""

        si_raw = item.get("si", item.get("sl", item.get("line_no")))
        si = "" if si_raw in (None, "") else str(si_raw).strip()
        extras: dict[str, str] = {}

        def _extra_put(key, value):
            if value in (None, ""):
                return
            nk = str(key).strip().lower().replace(" ", "_")
            if not nk or nk in extras:
                return
            extras[nk] = str(value).strip().replace(",", "")

        raw_cols = item.get("raw_columns") or item.get("extras") or {}
        if isinstance(raw_cols, dict):
            for key, value in raw_cols.items():
                _extra_put(key, value)
        for key in ("cs", "upc", "boxes", "box", "ctn", "pack", "strips", "dozen", "doz"):
            _extra_put(key, item.get(key))
        lines.append({
            "si": si,
            "name": name,
            "sku": str(item.get("sku") or item.get("pcode") or item.get("product_code") or "").strip(),
            "hsn_code": str(item.get("hsn_code") or item.get("hsn") or "").strip(),
            "quantity": qty,
            "unit_price": unit_price,
            "gst_rate": gst_rate,
            "mrp": mrp,
            "include": not unread,
            "confidence": confidence,
            "cs": extras.get("cs") or _raw_num("cs", "Cs"),
            "upc": extras.get("upc") or _raw_num("upc", "UPC"),
            "printed_gross_amt": _raw_num("printed_gross_amt", "gross_amt", "grossAmt", "amount"),
            "printed_taxable_amt": _raw_num("printed_taxable_amt", "taxable_amt", "taxableAmt"),
            "extras": extras,
        })
    overall_conf = raw.get("confidence")
    try:
        overall = float(overall_conf) if overall_conf not in (None, "") else None
    except (TypeError, ValueError):
        overall = None
    headers_in = raw.get("column_headers") or []
    column_headers = [str(h).strip() for h in headers_in if str(h or "").strip()] if isinstance(headers_in, list) else []
    return {
        "supplier_name": str(raw.get("supplier_name") or "").strip(),
        "supplier_gstin": str(raw.get("supplier_gstin") or "").strip(),
        "buyer_name": str(raw.get("buyer_name") or "").strip(),
        "buyer_gstin": str(raw.get("buyer_gstin") or "").strip(),
        "bill_number": str(raw.get("bill_number") or "").strip(),
        "bill_date": str(raw.get("bill_date") or "").strip(),
        "confidence": overall,
        "printed_line_count": _coerce_printed_line_count(raw, lines),
        "column_headers": column_headers,
        "lines": lines,
    }


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _coerce_printed_line_count(raw: dict[str, Any], lines: list[dict[str, Any]]) -> int | None:
    count = _coerce_int(raw.get("printed_line_count") or raw.get("line_count"))
    max_si = None
    for line in lines:
        si = _coerce_int(line.get("si"))
        if si is not None:
            max_si = si if max_si is None else max(max_si, si)
    if count and max_si:
        return max(count, max_si)
    return count or max_si


def expected_line_count(payload: dict[str, Any]) -> int:
    """How many numbered product rows the bill claims to have."""
    return _coerce_int(payload.get("printed_line_count")) or 0


def needs_extraction_continuation(payload: dict[str, Any], finish_reason: str | None) -> bool:
    """True when the model stopped early (token cap or fewer lines than last SI)."""
    lines = payload.get("lines") or []
    got = len(lines)
    expected = expected_line_count(payload)
    if finish_reason in ("length", "max_tokens"):
        return True
    return bool(expected) and got < expected


def last_extracted_si(payload: dict[str, Any]) -> int:
    """Highest SI on extracted lines, else the number of lines."""
    max_si = 0
    lines = payload.get("lines") or []
    for line in lines:
        si = _coerce_int(line.get("si"))
        if si is not None:
            max_si = max(max_si, si)
    return max_si or len(lines)


def should_probe_remaining_rows(payload: dict[str, Any], finish_reason: str | None) -> bool:
    """Always ask for the next SI window once a photo extract looks truncated.

    Mini (and even 4o with json_object) often returns exactly 20 rows and sets
    printed_line_count to 20, so `needs_extraction_continuation` stays false.
    """
    if needs_extraction_continuation(payload, finish_reason):
        return True
    got = len(payload.get("lines") or [])
    expected = expected_line_count(payload)
    if got >= MIN_LINES_TO_PROBE_MORE and (not expected or expected <= got):
        return True
    return False


def sort_extraction_lines_by_si(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the printed table order (SI) after chunked extracts are merged."""
    def sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, line = item
        si = _coerce_int(line.get("si"))
        return (si if si is not None else index + 1, index)

    return [line for _, line in sorted(enumerate(lines), key=sort_key)]


def merge_extraction_line_payloads(first: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Append continuation lines, skipping SI duplicates from the first batch."""
    merged = dict(first)
    existing_sis = {str(ln.get("si")) for ln in (first.get("lines") or []) if ln.get("si")}
    extra_lines = []
    for line in extra.get("lines") or []:
        si = str(line.get("si") or "")
        if si and si in existing_sis:
            continue
        extra_lines.append(line)
    merged["lines"] = sort_extraction_lines_by_si(list(first.get("lines") or []) + extra_lines)
    merged_count = _coerce_printed_line_count(
        {"printed_line_count": extra.get("printed_line_count") or first.get("printed_line_count")},
        merged["lines"],
    )
    merged["printed_line_count"] = merged_count
    if extra.get("column_headers") and not merged.get("column_headers"):
        merged["column_headers"] = extra["column_headers"]
    return merged


def _continuation_prompt(payload: dict[str, Any]) -> str:
    start = last_extracted_si(payload) + 1
    end = start + EXTRACT_CHUNK_SIZE - 1
    return _si_range_prompt(start, end, payload)


def _si_range_prompt(start: int, end: int, header: dict[str, Any] | None = None) -> str:
    headers = ""
    if header:
        known = header.get("column_headers") or []
        known_count = header.get("printed_line_count") or ""
        if known or known_count:
            headers = (
                f"\nKnown column headers: {known}. "
                f"Last SI reported so far: {known_count}.\n"
            )
    return (
        f"{EXTRACT_PROMPT}\n{headers}\n"
        f"THIS CALL: extract ONLY product rows whose SI is between {start} and {end} "
        f"inclusive, in order. If the table is unnumbered, extract the {start}th through "
        f"{end}th product row (1-based). Do not return rows outside that window. "
        f"Copy every extra pack/qty column (Cs, UPC, Boxes, Pack, Strips, …) into "
        f"raw_columns digit-for-digit; quantity is the loose/Pcs/Qty column only. "
        f"If a SI in this range is unreadable, still emit it with empty fields and low "
        f"confidence — do not skip numbers. If the printed table ends before SI {end}, "
        f"return the remaining real rows and stop. Set printed_line_count to the last "
        f"SI visible on the whole bill (not just this window)."
    )


def _image_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_openai_compatible(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    images: list[bytes],
    prompt: str = EXTRACT_PROMPT,
    max_tokens: int = EXTRACT_MAX_TOKENS,
) -> tuple[dict[str, Any], str | None]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise BusinessRuleError("openai package is not installed.") from exc

    if not api_key:
        raise BusinessRuleError("LLM API key is not configured for the selected provider.")

    # BUG-306: no timeout meant a hanging provider blocked the worker
    # indefinitely, leaving the ImportJob stuck in EXTRACTING forever.
    # Dense 30–80 line invoices need longer than 60s once max_tokens is raised.
    client = (
        OpenAI(api_key=api_key, base_url=base_url, timeout=EXTRACT_TIMEOUT_SECONDS)
        if base_url
        else OpenAI(api_key=api_key, timeout=EXTRACT_TIMEOUT_SECONDS)
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in images:
        mime = _detect_image_mime(image)
        content.append({
            "type": "image_url",
            # High-detail tiling is required to read a 30-row × 19-col DMS table
            # on a phone photo; "auto"/"low" is why we previously stopped at ~20.
            "image_url": {"url": _image_data_url(image, mime), "detail": "high"},
        })
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    choice = response.choices[0]
    text = choice.message.content or ""
    payload = _normalize_payload(_parse_json_content(text))
    return payload, getattr(choice, "finish_reason", None)


def _extract_claude(
    *,
    api_key: str,
    model: str,
    images: list[bytes],
    prompt: str = EXTRACT_PROMPT,
    max_tokens: int = EXTRACT_MAX_TOKENS,
) -> tuple[dict[str, Any], str | None]:
    try:
        import anthropic
    except ImportError as exc:
        raise BusinessRuleError("anthropic package is not installed.") from exc

    if not api_key:
        raise BusinessRuleError("ANTHROPIC_API_KEY is not configured.")

    client = anthropic.Anthropic(api_key=api_key, timeout=EXTRACT_TIMEOUT_SECONDS)
    content: list[dict[str, Any]] = []
    for image in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _detect_image_mime(image),
                "data": base64.standard_b64encode(image).decode("ascii"),
            },
        })
    content.append({"type": "text", "text": prompt})
    response = client.messages.create(
        model=model,
        # Dense GST invoices often have 30–80 lines; 4096 truncates mid-JSON.
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": content}],
    )
    text_parts = [
        block.text for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    payload = _normalize_payload(_parse_json_content("\n".join(text_parts)))
    return payload, getattr(response, "stop_reason", None)


def extract_purchase_bill(images: list[bytes]) -> dict[str, Any]:
    """Extract structured purchase-bill lines from page images via configured LLM.

    Dense GST photos are pulled in SI windows (1–15, 16–30, …) with a zoomed
    crop of the matching table band. A single json_object call otherwise stops
    around 20 rows even when max_tokens is large.
    """
    if not images:
        raise BusinessRuleError("No images provided for extraction.")

    provider = _provider()
    model = _bill_model_for(provider)

    def _call(
        prompt: str,
        call_images: list[bytes],
        *,
        max_tokens: int = EXTRACT_MAX_TOKENS,
    ) -> tuple[dict[str, Any], str | None]:
        if provider == "openai":
            return _extract_openai_compatible(
                api_key=getattr(settings, "OPENAI_API_KEY", "") or "",
                base_url=None,
                model=model,
                images=call_images,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        if provider == "deepseek":
            return _extract_openai_compatible(
                api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "",
                base_url=getattr(settings, "DEEPSEEK_BASE_URL", None) or "https://api.deepseek.com",
                model=model,
                images=call_images,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        if provider == "claude":
            return _extract_claude(
                api_key=getattr(settings, "ANTHROPIC_API_KEY", "") or "",
                model=model,
                images=call_images,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        raise BusinessRuleError(
            f"Unsupported LLM_PROVIDER '{provider}'. Use openai, deepseek, or claude."
        )

    start = 1
    payload: dict[str, Any] | None = None
    finish_reason: str | None = None
    split_cache: dict[int, dict[str, bytes]] = {}
    for chunk_index in range(MAX_EXTRACT_CHUNKS):
        end = start + EXTRACT_CHUNK_SIZE - 1
        call_images = views_for_si_range(images, start=start, cache=split_cache)
        prompt = _si_range_prompt(start, end, payload)
        try:
            extra, finish_reason = _call(prompt, call_images)
        except Exception:
            if payload is not None:
                logger.exception("Bill extract chunk SI %s-%s failed; keeping prior rows", start, end)
                break
            raise
        if payload is None:
            payload = extra
            payload["lines"] = sort_extraction_lines_by_si(list(payload.get("lines") or []))
        else:
            before = len(payload.get("lines") or [])
            payload = merge_extraction_line_payloads(payload, extra)
            if len(payload.get("lines") or []) <= before:
                break
        got = len(payload.get("lines") or [])
        logger.info(
            "Bill extract chunk %s SI %s-%s model=%s lines_so_far=%s printed_line_count=%s finish=%s",
            chunk_index + 1, start, end, model, got,
            payload.get("printed_line_count"), finish_reason,
        )
        next_start = last_extracted_si(payload) + 1
        expected = expected_line_count(payload)
        if expected and got >= expected and chunk_index > 0:
            break
        more_expected = bool(expected) and got < expected
        more_window = len(extra.get("lines") or []) >= MIN_LINES_TO_PROBE_MORE
        if chunk_index == 0 and should_probe_remaining_rows(payload, finish_reason):
            start = next_start if next_start > start else start + EXTRACT_CHUNK_SIZE
            continue
        if more_expected or more_window:
            start = next_start if next_start > start else start + EXTRACT_CHUNK_SIZE
            continue
        break

    if payload is None:
        raise BusinessRuleError("LLM returned no extraction payload.")
    payload["lines"] = sort_extraction_lines_by_si(list(payload.get("lines") or []))
    return payload


def llm_api_key_configured() -> bool:
    provider = _provider()
    if provider == "openai":
        return bool(getattr(settings, "OPENAI_API_KEY", "") or "")
    if provider == "deepseek":
        return bool(getattr(settings, "DEEPSEEK_API_KEY", "") or "")
    if provider == "claude":
        return bool(getattr(settings, "ANTHROPIC_API_KEY", "") or "")
    return False


def chat_with_tools(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Text chat with optional OpenAI-style tools.
    Returns {content, tool_calls:[{id,name,arguments}], usage:{tokens_in,tokens_out}, model}.
    Raises BusinessRuleError if provider/key missing.
    """
    provider = _provider()
    model = _model_for(provider)
    tools = tools or []

    if provider in ("openai", "deepseek"):
        api_key = (
            (getattr(settings, "OPENAI_API_KEY", "") or "")
            if provider == "openai"
            else (getattr(settings, "DEEPSEEK_API_KEY", "") or "")
        )
        base_url = (
            None
            if provider == "openai"
            else (getattr(settings, "DEEPSEEK_BASE_URL", None) or "https://api.deepseek.com")
        )
        if not api_key:
            raise BusinessRuleError("LLM API key is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise BusinessRuleError("openai package is not installed.") from exc
        client = (
            OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
            if base_url
            else OpenAI(api_key=api_key, timeout=60.0)
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0].message
        tool_calls = []
        for tc in getattr(choice, "tool_calls", None) or []:
            args_raw = tc.function.arguments if tc.function else "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name if tc.function else "",
                "arguments": args,
            })
        usage = getattr(response, "usage", None)
        return {
            "content": choice.content or "",
            "tool_calls": tool_calls,
            "usage": {
                "tokens_in": getattr(usage, "prompt_tokens", 0) or 0,
                "tokens_out": getattr(usage, "completion_tokens", 0) or 0,
            },
            "model": model,
        }

    if provider == "claude":
        # Tool-calling via Anthropic is supported but CI often lacks keys —
        # raise so caller falls back to rules.
        api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
        if not api_key:
            raise BusinessRuleError("ANTHROPIC_API_KEY is not configured.")
        try:
            import anthropic
        except ImportError as exc:
            raise BusinessRuleError("anthropic package is not installed.") from exc
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
        # Flatten OpenAI-style tools to Anthropic tools
        anth_tools = []
        for t in tools:
            fn = t.get("function") or {}
            anth_tools.append({
                "name": fn.get("name") or t.get("name"),
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        sys_msgs = [m["content"] for m in messages if m.get("role") == "system"]
        user_msgs = [m for m in messages if m.get("role") != "system"]
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0,
            system="\n".join(sys_msgs) or "You are a business insights assistant.",
            messages=[{"role": m["role"], "content": m["content"]} for m in user_msgs if m.get("role") in ("user", "assistant")],
            tools=anth_tools or anthropic.NOT_GIVEN,
        )
        content_text = ""
        tool_calls = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                content_text += block.text or ""
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input if isinstance(block.input, dict) else {},
                })
        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "usage": {
                "tokens_in": getattr(response.usage, "input_tokens", 0) or 0,
                "tokens_out": getattr(response.usage, "output_tokens", 0) or 0,
            },
            "model": model,
        }

    raise BusinessRuleError(f"Unsupported LLM_PROVIDER '{provider}'.")
