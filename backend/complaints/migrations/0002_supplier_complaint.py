import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0056_whatsapp_webhook_token"),
        ("complaints", "0001_growth_os"),
        ("core", "0033_rls_lead_ingest_job"),
        ("masters", "0021_customer_coordinates"),
        ("purchases", "0035_sales_purchase_ux_plan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplierComplaint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.CharField(blank=True, max_length=32)),
                ("category", models.CharField(choices=[("DAMAGED", "Damaged"), ("WRONG_DELIVERY", "Wrong Delivery"), ("QUALITY", "Quality"), ("OTHER", "Other")], max_length=16)),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("INSPECTING", "Inspecting"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("RESOLVED", "Resolved")], default="OPEN", max_length=16)),
                ("inspection_notes", models.TextField(blank=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_complaints", to="accounts.companyuser")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("purchase_debit_note", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="supplier_complaints", to="purchases.purchasedebitnote")),
                ("source_invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="supplier_complaints", to="purchases.purchaseinvoice")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="supplier_complaints", to="masters.supplier")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupplierComplaintAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("complaint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="complaints.suppliercomplaint")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("file", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="core.fileasset")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="suppliercomplaint",
            index=models.Index(fields=["company", "status"], name="scomp_company_status_idx"),
        ),
        migrations.AddIndex(
            model_name="suppliercomplaint",
            index=models.Index(fields=["company", "supplier"], name="scomp_company_supplier_idx"),
        ),
        migrations.AddIndex(
            model_name="suppliercomplaint",
            index=models.Index(fields=["company", "source_invoice"], name="scomp_company_invoice_idx"),
        ),
        migrations.AddConstraint(
            model_name="suppliercomplaint",
            constraint=models.UniqueConstraint(condition=models.Q(("number", ""), _negated=True), fields=("company", "number"), name="uniq_scomp_number_per_company"),
        ),
    ]
