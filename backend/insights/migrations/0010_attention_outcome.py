import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0056_whatsapp_webhook_token"),
        ("insights", "0009_attention_assignment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AttentionOutcome",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dedupe_key", models.CharField(max_length=191)),
                ("code", models.CharField(max_length=64)),
                ("outcome", models.CharField(choices=[("resolved", "Resolved"), ("dismissed", "Dismissed")], max_length=16)),
                ("within_window", models.BooleanField(default=False)),
                ("metric_improved", models.BooleanField(blank=True, null=True)),
                ("recorded_at", models.DateTimeField()),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="attentionoutcome",
            index=models.Index(fields=["company", "code"], name="attn_outcome_company_code_idx"),
        ),
        migrations.AddConstraint(
            model_name="attentionoutcome",
            constraint=models.UniqueConstraint(fields=("company", "dedupe_key"), name="uniq_attention_outcome_per_company"),
        ),
    ]
