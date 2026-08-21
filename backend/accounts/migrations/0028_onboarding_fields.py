from django.db import migrations, models
from django.utils import timezone


def backfill_onboarding(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    Product = apps.get_model("masters", "Product")
    SalesInvoice = apps.get_model("sales", "SalesInvoice")
    now = timezone.now()

    for company in Company.objects.all().iterator():
        has_completed_sale = SalesInvoice.objects.filter(
            company_id=company.pk,
            status="COMPLETED",
        ).exists()
        if has_completed_sale:
            if company.tax_profile_confirmed_at is None:
                company.tax_profile_confirmed_at = now
                company.save(update_fields=["tax_profile_confirmed_at"])
            continue

        has_existing_progress = bool(
            (company.address or "").strip()
            or (company.gstin or "").strip()
            or Product.objects.filter(company_id=company.pk).exists()
        )
        if not has_existing_progress:
            continue

        update_fields = []
        if company.onboarding_dismissed_at is None:
            company.onboarding_dismissed_at = now
            update_fields.append("onboarding_dismissed_at")
        tax_looks_configured = bool((company.gstin or "").strip()) or company.registration_type in (
            "COMPOSITION",
            "UNREGISTERED",
        )
        if tax_looks_configured and company.tax_profile_confirmed_at is None:
            company.tax_profile_confirmed_at = now
            update_fields.append("tax_profile_confirmed_at")
        if update_fields:
            company.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0027_uxw2_assume_local_state_default"),
        ("masters", "0007_expensecategory_paymentmode"),
        ("sales", "0031_tax12_cess_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="onboarding_dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="tax_profile_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="onboarding_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_onboarding, migrations.RunPython.noop),
    ]
