import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0059_user_session_version"),
        ("masters", "0021_customer_coordinates"),
        ("inventory", "0020_track_readiness"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to="inventory.batchlot")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to="masters.product")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to="inventory.warehouse")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddIndex(
            model_name="stockreservation",
            index=models.Index(fields=["company", "released_at", "expires_at"], name="inv_reserve_expiry_idx"),
        ),
        migrations.AddField(
            model_name="stocktransfer",
            name="transfer_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AlterField(
            model_name="stocktransfer",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("DISPATCHED", "Dispatched"),
                    ("COMPLETED", "Completed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="DRAFT",
                max_length=12,
            ),
        ),
    ]
