"""Item custom-field definitions, import matching, search, and value coercion."""

from __future__ import annotations

import re
from typing import Any

from django.db.models import Q
from rest_framework.exceptions import ValidationError

MAX_ACTIVE_FIELDS = 20
MAX_OPTIONS = 50
MAX_KEY_LEN = 64
MAX_LABEL_LEN = 80
MAX_OPTION_LEN = 80
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_SEP_RE = re.compile(r"[\s_\-]+")
BRAND_SEED_KEYS = ("brandCode", "brandForm", "subBrandForm")
BRAND_SEED_LABELS = {
    "brandCode": "Brand code",
    "brandForm": "Brand form",
    "subBrandForm": "Sub brand form",
}


def normalize_header(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    if not raw:
        return ""
    return _SEP_RE.sub(" ", raw).strip()


def _reserved_normalized() -> set[str]:
    from imports.services import MASTER_COLUMN_ALIASES, PRODUCTS_ITEM_COLUMNS

    names = set(PRODUCTS_ITEM_COLUMNS) | {
        "id", "status", "created_at", "updated_at", "brand", "category_name",
        "hsn", "quantity", "custom_fields", "customfields",
        # Django JSONField lookup / transform names — unsafe as stored keys.
        "exact", "iexact", "contains", "icontains", "in", "gt", "gte", "lt", "lte",
        "startswith", "istartswith", "endswith", "iendswith", "range", "isnull",
        "regex", "iregex", "contained_by", "has_key", "has_keys", "has_any_keys",
    }
    for aliases in MASTER_COLUMN_ALIASES.values():
        names.update(aliases)
    return {normalize_header(name) for name in names if name}


def omit_empty(values: dict | None) -> dict:
    out = {}
    for key, raw in (values or {}).items():
        text = str(raw).strip()
        if text:
            out[str(key)] = text
    return out


def surface_values(values: dict | None, defs: list[dict] | None) -> dict:
    """Public GET payload: drop empties and inactive keys. Missing defs fail closed."""
    cleaned = omit_empty(values)
    active_keys = {row["key"] for row in (defs or []) if row.get("active")}
    return {key: value for key, value in cleaned.items() if key in active_keys}


def distinct_values_for_keys(company, keys: list[str]) -> dict[str, list[str]]:
    """Distinct stored values per key (case-insensitive), preserving first spelling."""
    if not keys:
        return {}
    from masters.models import Product

    allowed = list(dict.fromkeys(keys))
    out = {key: [] for key in allowed}
    seen = {key: set() for key in allowed}
    qs = (
        Product.objects.filter(company=company)
        .exclude(custom_fields={})
        .values_list("custom_fields", flat=True)
    )
    for fields in qs.iterator(chunk_size=500):
        if not isinstance(fields, dict):
            continue
        for key in allowed:
            text = str(fields.get(key) or "").strip()
            if not text:
                continue
            folded = text.casefold()
            if folded in seen[key]:
                continue
            seen[key].add(folded)
            out[key].append(text)
    return out


def normalize_stored_defs(rows: list | None) -> list[dict]:
    """Fill type/active on legacy {key,label} rows. Empty stays empty."""
    cleaned = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        label = str(row.get("label") or "").strip()
        if not key or not label or key.casefold() in seen:
            continue
        seen.add(key.casefold())
        field_type = str(row.get("type") or "text").strip().casefold()
        if field_type not in {"text", "list"}:
            field_type = "text"
        options = []
        if field_type == "list":
            options = _clean_option_list(row.get("options") or [], allow_empty=True)
        cleaned.append({
            "key": key[:MAX_KEY_LEN],
            "label": label[:MAX_LABEL_LEN],
            "type": field_type,
            "active": bool(row.get("active", True)),
            "options": options,
        })
    actives = [row for row in cleaned if row["active"]]
    inactives = [row for row in cleaned if not row["active"]]
    return actives + inactives


def active_defs(company) -> list[dict]:
    return [row for row in normalize_stored_defs(getattr(company, "item_custom_field_defs", None)) if row["active"]]


def defs_for_company(company) -> list[dict]:
    return normalize_stored_defs(getattr(company, "item_custom_field_defs", None))


def _clean_option_list(raw, *, allow_empty: bool) -> list[str]:
    options = []
    seen = set()
    for item in raw or []:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > MAX_OPTION_LEN:
            raise ValidationError(f"List option cannot exceed {MAX_OPTION_LEN} characters.")
        folded = text.casefold()
        if folded in seen:
            raise ValidationError("List options must be unique (case-insensitive).")
        seen.add(folded)
        options.append(text[:MAX_OPTION_LEN])
    if not allow_empty and not options:
        raise ValidationError("List fields require at least one option.")
    if len(options) > MAX_OPTIONS:
        raise ValidationError(f"A list field can have at most {MAX_OPTIONS} options.")
    return options


def _match_option(value: str, options: list[str]) -> str | None:
    folded = value.casefold()
    for option in options:
        if option.casefold() == folded:
            return option
    return None


def _assert_active_tokens_unique(parsed: list[dict]) -> None:
    """Active key and label tokens share one namespace so import headers cannot mis-map."""
    owner: dict[str, str] = {}
    for row in parsed:
        if not row.get("active"):
            continue
        for raw in (row["key"], row["label"]):
            token = normalize_header(raw)
            if not token:
                continue
            previous = owner.get(token)
            if previous and previous != row["key"]:
                raise ValidationError(
                    f"Active custom field '{raw}' collides with another field's key or label."
                )
            owner[token] = row["key"]


def validate_definitions(existing: list | None, incoming: list | None) -> list[dict]:
    if incoming is None:
        incoming = []
    if not isinstance(incoming, list):
        raise ValidationError("Must be a list of key/label objects.")

    existing_norm = normalize_stored_defs(existing)
    existing_by_fold = {row["key"].casefold(): row for row in existing_norm}
    reserved = _reserved_normalized()

    parsed: list[dict] = []
    seen_keys: set[str] = set()
    active_labels: set[str] = set()

    for row in incoming:
        if not isinstance(row, dict):
            raise ValidationError("Each custom field definition must be an object.")
        key = str(row.get("key") or "").strip()
        label = str(row.get("label") or "").strip()
        if not key:
            raise ValidationError("Custom field key is required.")
        if not label:
            raise ValidationError("Custom field label is required.")
        if len(key) > MAX_KEY_LEN:
            raise ValidationError(f"Custom field key cannot exceed {MAX_KEY_LEN} characters.")
        if len(label) > MAX_LABEL_LEN:
            raise ValidationError(f"Custom field label cannot exceed {MAX_LABEL_LEN} characters.")
        if not KEY_RE.match(key):
            raise ValidationError(
                "Custom field key must start with a letter and contain only letters and digits."
            )
        if normalize_header(key) in reserved:
            raise ValidationError(f"Custom field key '{key}' collides with a reserved item column.")
        if normalize_header(label) in reserved:
            raise ValidationError(f"Custom field label '{label}' collides with a reserved item column.")
        folded = key.casefold()
        if folded in seen_keys:
            raise ValidationError("Custom field keys must be unique.")
        seen_keys.add(folded)
        prior = existing_by_fold.get(folded)
        if prior and prior["key"] != key:
            raise ValidationError("A previously used custom field key cannot be reused with different spelling.")
        field_type = str(row.get("type") or (prior or {}).get("type") or "text").strip().casefold()
        if field_type not in {"text", "list"}:
            raise ValidationError("Custom field type must be text or list.")
        if prior and prior["type"] != field_type:
            raise ValidationError("Custom field type cannot be changed after save.")
        active = bool(row["active"]) if "active" in row else bool((prior or {}).get("active", True))
        options = []
        if field_type == "list":
            options = _clean_option_list(row.get("options") if "options" in row else (prior or {}).get("options"), allow_empty=not active)
        if active:
            label_fold = normalize_header(label)
            if label_fold in active_labels:
                raise ValidationError("Active custom field labels must be unique.")
            active_labels.add(label_fold)
        parsed.append({
            "key": key,
            "label": label,
            "type": field_type,
            "active": active,
            "options": options,
        })

    _assert_active_tokens_unique(parsed)

    incoming_folds = {row["key"].casefold() for row in parsed}
    missing = [row["key"] for fold, row in existing_by_fold.items() if fold not in incoming_folds]
    if missing:
        raise ValidationError(
            "Removed custom fields must be kept inactive, not deleted from the list."
        )
    active_count = sum(1 for row in parsed if row["active"])
    if active_count > MAX_ACTIVE_FIELDS:
        raise ValidationError(f"At most {MAX_ACTIVE_FIELDS} active custom fields are allowed.")
    previously_active = {row["key"].casefold() for row in existing_norm if row["active"]}
    stable_actives = []
    reactivated = []
    for row in parsed:
        if not row["active"]:
            continue
        folded = row["key"].casefold()
        if folded in existing_by_fold and folded not in previously_active:
            reactivated.append(row)
        else:
            stable_actives.append(row)
    inactives = [row for row in parsed if not row["active"]]
    return stable_actives + reactivated + inactives


def resolve_import_columns(headers: list[str], defs: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Map normalized header → destination key. Duplicate targets are errors."""
    actives = [row for row in defs if row.get("active")]
    by_norm: dict[str, str] = {}
    mapping: dict[str, str] = {}
    used_keys: dict[str, str] = {}
    errors: list[str] = []
    for row in actives:
        for raw in (row.get("key"), row.get("label")):
            token = normalize_header(raw)
            if not token:
                continue
            existing = by_norm.get(token)
            if existing and existing != row["key"]:
                errors.append(
                    f"Custom field '{raw}' collides with '{existing}' and cannot be used as an import header."
                )
                continue
            by_norm[token] = row["key"]
    for header in headers:
        norm = normalize_header(header)
        if not norm:
            continue
        dest = by_norm.get(norm)
        if not dest:
            continue
        if dest in used_keys:
            errors.append(
                f"Duplicate custom field columns map to '{dest}' ({used_keys[dest]!r} and {header!r})."
            )
            continue
        used_keys[dest] = norm
        mapping[norm] = dest
    return mapping, errors


def values_from_row(row: dict, header_map: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for source, value in (row or {}).items():
        dest = header_map.get(normalize_header(source))
        if not dest:
            continue
        text = str(value or "").strip()
        if text:
            out[dest] = text
    return out


_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _snake_key(key: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", str(key or "")).lower()


def _canonicalize_incoming_keys(raw: dict, defs: list[dict]) -> dict:
    """Map parser-mangled keys (brand_code) back to the stored camelCase key."""
    aliases: dict[str, str] = {}
    for row in defs:
        if not row.get("active"):
            continue
        key = str(row.get("key") or "")
        if not key:
            continue
        aliases[key] = key
        aliases[key.casefold()] = key
        aliases[_snake_key(key)] = key
    out: dict[str, object] = {}
    for src, value in raw.items():
        dest = aliases.get(str(src)) or aliases.get(str(src).casefold()) or str(src)
        out[dest] = value
    return out


def coerce_values(raw, defs: list[dict], existing: dict | None, *, replace_active: bool = True) -> dict:
    existing = omit_empty(existing if isinstance(existing, dict) else {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValidationError({"custom_fields": "Must be an object."})
    raw = _canonicalize_incoming_keys(raw, defs)
    actives = [row for row in defs if row.get("active")]
    active_keys = {row["key"] for row in actives}
    if replace_active:
        result = {key: value for key, value in existing.items() if key not in active_keys}
    else:
        result = dict(existing)

    for key in raw:
        if key not in active_keys:
            if key in existing:
                continue
            raise ValidationError({"custom_fields": f"Unknown custom field '{key}'."})

    for row in actives:
        if row["key"] not in raw:
            continue
        text = str(raw.get(row["key"]) or "").strip()
        if not text:
            if replace_active:
                result.pop(row["key"], None)
            continue
        if row["type"] == "list":
            options = row.get("options") or []
            matched = _match_option(text, options)
            stored = str(existing.get(row["key"]) or "").strip()
            if matched is None and stored.casefold() != text.casefold():
                raise ValidationError(
                    {"custom_fields": f"'{text}' is not a valid option for '{row['label']}'."}
                )
            result[row["key"]] = matched or stored or text
        else:
            result[row["key"]] = text
    return omit_empty(result)


def build_search_q(term: str, defs: list[dict], prefix: str = "") -> Q:
    query = Q()
    if not (term or "").strip():
        return query
    path = f"{prefix}custom_fields" if prefix else "custom_fields"
    for row in defs:
        if not row.get("active"):
            continue
        key = row.get("key") or ""
        if not KEY_RE.match(key):
            continue
        query |= Q(**{f"{path}__{key}__icontains": term})
    return query


def apply_cf_filters(qs, query_params, defs: list[dict], prefix: str = ""):
    list_keys = {
        row["key"]
        for row in defs
        if row.get("active") and row.get("type") == "list" and KEY_RE.match(row.get("key") or "")
    }
    any_keys = {
        row["key"]
        for row in defs
        if row.get("active") and KEY_RE.match(row.get("key") or "")
    }
    path = f"{prefix}custom_fields" if prefix else "custom_fields"
    grouped: dict[str, list[str]] = {}
    if hasattr(query_params, "lists"):
        items = list(query_params.lists())
    else:
        items = [
            (key, value if isinstance(value, (list, tuple)) else [value])
            for key, value in dict(query_params).items()
        ]
    for name, values in items:
        dotted = str(name)
        if dotted.startswith("cf."):
            field_key = dotted[3:]
            allowed = list_keys
        elif dotted.startswith("custom_fields."):
            field_key = dotted[len("custom_fields.") :]
            allowed = any_keys
            if field_key not in allowed and field_key == "brand":
                field_key = next((k for k in BRAND_SEED_KEYS if k in allowed), field_key)
        else:
            continue
        if field_key not in allowed:
            continue
        cleaned = [str(v).strip() for v in values if str(v or "").strip()]
        if cleaned:
            grouped.setdefault(field_key, []).extend(cleaned)
    for field_key, values in grouped.items():
        clause = Q()
        for value in values:
            clause |= Q(**{f"{path}__{field_key}__iexact": value})
        qs = qs.filter(clause)
    return qs
