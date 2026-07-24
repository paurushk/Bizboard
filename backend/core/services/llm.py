"""Configurable LLM client for purchase-bill / rate-list vision extraction."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from django.conf import settings

from core.exceptions import BusinessRuleError

EXTRACT_PROMPT = """Extract purchase bill or rate-list line items from the attached document image(s).
Return ONLY valid JSON (no markdown) with this exact shape:
{
  "supplier_name": "",
  "supplier_gstin": "",
  "bill_number": "",
  "bill_date": "",
  "lines": [
    {
      "name": "",
      "sku": "",
      "hsn_code": "",
      "quantity": "1",
      "unit_price": "0",
      "gst_rate": "18",
      "mrp": "0"
    }
  ]
}
Rules:
- quantity, unit_price, gst_rate, mrp must be numeric strings.
- gst_rate must be one of 0, 0.25, 3, 5, 12, 18, 28 when known; else 18.
- Skip totals, tax summary, and header-only rows.
- If a field is unknown use "" or "0" as appropriate.
"""

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    # DeepSeek chat has no vision — use a vision-capable model when provider=deepseek.
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
        lines.append({
            "name": name,
            "sku": str(item.get("sku") or "").strip(),
            "hsn_code": str(item.get("hsn_code") or item.get("hsn") or "").strip(),
            "quantity": str(item.get("quantity") or "1").strip() or "1",
            "unit_price": str(item.get("unit_price") or item.get("rate") or "0").strip() or "0",
            "gst_rate": str(item.get("gst_rate") or "18").strip() or "18",
            "mrp": str(item.get("mrp") or "0").strip() or "0",
            "include": True,
        })
    return {
        "supplier_name": str(raw.get("supplier_name") or "").strip(),
        "supplier_gstin": str(raw.get("supplier_gstin") or "").strip(),
        "bill_number": str(raw.get("bill_number") or "").strip(),
        "bill_date": str(raw.get("bill_date") or "").strip(),
        "lines": lines,
    }


def _image_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_openai_compatible(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    images: list[bytes],
) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise BusinessRuleError("openai package is not installed.") from exc

    if not api_key:
        raise BusinessRuleError("LLM API key is not configured for the selected provider.")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    content: list[dict[str, Any]] = [{"type": "text", "text": EXTRACT_PROMPT}]
    for image in images:
        mime = _detect_image_mime(image)
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_data_url(image, mime)},
        })
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or ""
    return _normalize_payload(_parse_json_content(text))


def _extract_claude(*, api_key: str, model: str, images: list[bytes]) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as exc:
        raise BusinessRuleError("anthropic package is not installed.") from exc

    if not api_key:
        raise BusinessRuleError("ANTHROPIC_API_KEY is not configured.")

    client = anthropic.Anthropic(api_key=api_key)
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
    content.append({"type": "text", "text": EXTRACT_PROMPT})
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": content}],
    )
    text_parts = [
        block.text for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    return _normalize_payload(_parse_json_content("\n".join(text_parts)))


def extract_purchase_bill(images: list[bytes]) -> dict[str, Any]:
    """Extract structured purchase-bill lines from page images via configured LLM."""
    if not images:
        raise BusinessRuleError("No images provided for extraction.")

    provider = _provider()
    model = _model_for(provider)

    if provider == "openai":
        return _extract_openai_compatible(
            api_key=getattr(settings, "OPENAI_API_KEY", "") or "",
            base_url=None,
            model=model,
            images=images,
        )
    if provider == "deepseek":
        return _extract_openai_compatible(
            api_key=getattr(settings, "DEEPSEEK_API_KEY", "") or "",
            base_url=getattr(settings, "DEEPSEEK_BASE_URL", None) or "https://api.deepseek.com",
            model=model,
            images=images,
        )
    if provider == "claude":
        return _extract_claude(
            api_key=getattr(settings, "ANTHROPIC_API_KEY", "") or "",
            model=model,
            images=images,
        )
    raise BusinessRuleError(
        f"Unsupported LLM_PROVIDER '{provider}'. Use openai, deepseek, or claude."
    )
