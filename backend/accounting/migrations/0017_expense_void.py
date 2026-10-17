from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0016_cash_shift_adjustment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="status",
            field=models.CharField(
                choices=[("ACTIVE", "Active"), ("VOID", "Void")],
                db_index=True, default="ACTIVE", max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="voided_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="void_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
