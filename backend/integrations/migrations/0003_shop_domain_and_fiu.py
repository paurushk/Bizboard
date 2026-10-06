from django.db import migrations, models


def backfill_shop_domain(apps, schema_editor):
    Connection = apps.get_model("integrations", "IntegrationConnection")
    seen = {}
    for row in Connection.objects.filter(provider="SHOPIFY", status="ACTIVE"):
        meta = row.metadata or {}
        domain = str(meta.get("shop_domain") or "").strip().lower()
        if not domain:
            continue
        seen.setdefault(domain, []).append(row.pk)
        row.shop_domain = domain
        row.save(update_fields=["shop_domain"])
    clashes = {domain: ids for domain, ids in seen.items() if len(ids) > 1}
    if clashes:
        raise RuntimeError(
            "Two active Shopify connections share a domain. Deactivate one and rerun. "
            f"{clashes}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_track_readiness"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconnection",
            name="shop_domain",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="integrationconnection",
            name="provider",
            field=models.CharField(
                choices=[
                    ("TALLY", "Tally"),
                    ("WHATSAPP", "Whatsapp"),
                    ("BUSY", "Busy"),
                    ("ZOHO", "Zoho"),
                    ("SHOPIFY", "Shopify"),
                    ("FIU", "Fiu"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(backfill_shop_domain, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="integrationconnection",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="ACTIVE") & ~models.Q(shop_domain=""),
                fields=("shop_domain",),
                name="uniq_active_shopify_domain",
            ),
        ),
    ]
