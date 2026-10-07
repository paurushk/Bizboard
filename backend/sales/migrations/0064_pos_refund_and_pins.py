from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def copy_owner_pins(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    CompanyUser = apps.get_model("accounts", "CompanyUser")
    Pin = apps.get_model("sales", "PosApproverPin")
    for company in Company.objects.all().iterator():
        flags = dict(company.feature_flags or {})
        hashed = flags.get("pos_owner_pin_hash")
        if not hashed:
            continue
        owner = CompanyUser.objects.filter(company=company, role="OWNER").order_by("id").first()
        if owner is None or not owner.user_id:
            continue
        Pin.objects.get_or_create(
            company=company,
            user_id=owner.user_id,
            defaults={"pin_hash": hashed, "set_at": timezone_now()},
        )
        flags.pop("pos_owner_pin_hash", None)
        company.feature_flags = flags
        company.save(update_fields=["feature_flags"])


def timezone_now():
    return django.utils.timezone.now()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0015_pos_shift_terminal"),
        ("payments", "0036_receipt_shift"),
        ("sales", "0063_stop_stock_released"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="pos_offline",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="salesperson",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pos_sales",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="terminal_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="terminal_label",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="salesitem",
            name="price_override_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="PosApproverPin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("pin_hash", models.CharField(max_length=128)),
                ("set_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pos_approver_pins", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="posapproverpin",
            constraint=models.UniqueConstraint(fields=("company", "user"), name="uniq_pos_approver_pin"),
        ),
        migrations.CreateModel(
            name="PosCounterRefund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("mode", models.CharField(choices=[("CASH", "Cash"), ("BANK", "Bank"), ("ADVANCE", "Advance")], max_length=12)),
                ("status", models.CharField(choices=[("ADVANCE", "Advance"), ("POSTED", "Posted"), ("PENDING_GATEWAY", "Pending Gateway")], default="POSTED", max_length=20)),
                ("refund_date", models.DateField(default=django.utils.timezone.localdate)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=64)),
                ("bank_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_refunds", to="payments.bankaccount")),
                ("cashier", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_refunds", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_refunds", to="masters.customer")),
                ("sales_return", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pos_refunds", to="sales.salesreturn")),
                ("shift", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="refunds", to="accounting.cashshiftregister")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="poscounterrefund",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("company", "idempotency_key"),
                name="uniq_pos_refund_idempotency",
            ),
        ),
        migrations.RunPython(copy_owner_pins, migrations.RunPython.noop),
    ]
