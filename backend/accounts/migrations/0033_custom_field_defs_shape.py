from django.db import migrations


BRAND_KEYS = ("brandCode", "brandForm", "subBrandForm")
BRAND_LABELS = {
    "brandCode": "Brand code",
    "brandForm": "Brand form",
    "subBrandForm": "Sub brand form",
}


def _normalize_row(row, *, default_active=True):
    if not isinstance(row, dict):
        return None
    key = str(row.get("key") or "").strip()
    label = str(row.get("label") or "").strip()
    if not key or not label:
        return None
    field_type = str(row.get("type") or "text").strip().lower()
    if field_type not in {"text", "list"}:
        field_type = "text"
    options = []
    if field_type == "list":
        seen = set()
        for item in row.get("options") or []:
            text = str(item or "").strip()
            if text and text.casefold() not in seen:
                seen.add(text.casefold())
                options.append(text)
    return {
        "key": key[:64],
        "label": label[:80],
        "type": field_type,
        "active": bool(row.get("active", default_active)),
        "options": options,
    }


def forwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    Product = apps.get_model("masters", "Product")

    for company in Company.objects.all():
        raw = list(company.item_custom_field_defs or [])
        normalized = []
        seen = set()
        for row in raw:
            parsed = _normalize_row(row)
            if parsed is None or parsed["key"].casefold() in seen:
                continue
            seen.add(parsed["key"].casefold())
            normalized.append(parsed)

        has_brand_def = bool(seen & {k.casefold() for k in BRAND_KEYS})
        has_brand_value = False
        for product in Product.objects.filter(company_id=company.pk).only("custom_fields").iterator():
            fields = product.custom_fields if isinstance(product.custom_fields, dict) else {}
            if any(key in fields for key in BRAND_KEYS):
                has_brand_value = True
                break
        if has_brand_def or has_brand_value:
            by_fold = {row["key"].casefold(): row for row in normalized}
            for key in BRAND_KEYS:
                if key.casefold() not in by_fold:
                    normalized.append({
                        "key": key,
                        "label": BRAND_LABELS[key],
                        "type": "text",
                        "active": True,
                        "options": [],
                    })
            actives = [row for row in normalized if row["active"]]
            inactives = [row for row in normalized if not row["active"]]
            company.item_custom_field_defs = actives + inactives
        else:
            company.item_custom_field_defs = normalized
        company.save(update_fields=["item_custom_field_defs"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0032_password_reset_jti"),
        ("masters", "0008_item_godown_expiry"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
