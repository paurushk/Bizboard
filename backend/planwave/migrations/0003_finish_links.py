from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planwave", "0002_blocked_credit_global"),
        ("inventory", "0023_planwave_remaining"),
        ("accounts", "0060_planwave_remaining"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="itcbillcheck",
            name="blocked_credit",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="itcbillcheck",
            name="claimed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="itcbillcheck",
            name="deadline_status",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.CreateModel(
            name="UserWarehouseAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_default", models.BooleanField(default=False)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouse_access", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="user_access", to="inventory.warehouse")),
            ],
        ),
        migrations.CreateModel(
            name="PosCartHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("expires_at", models.DateTimeField()),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="userwarehouseaccess",
            constraint=models.UniqueConstraint(fields=("company", "user", "warehouse"), name="uniq_user_warehouse"),
        ),
    ]
