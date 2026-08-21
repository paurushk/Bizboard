import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0026_sprint_d_billing_override"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("slug", models.SlugField(unique=True)),
                ("seat_limit", models.PositiveIntegerField(default=1)),
                ("modules", models.JSONField(blank=True, default=dict)),
                ("price_paise", models.PositiveIntegerField(default=0)),
                ("razorpay_plan_id", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["price_paise", "name"]},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("trial", "Trial"), ("active", "Active"), ("past_due", "Past Due"), ("suspended", "Suspended")], default="trial", max_length=16)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("razorpay_subscription_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="saas_subscription", to="accounts.company")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="billing.plan")),
            ],
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["status", "trial_ends_at"], name="billing_sub_status_trial_idx"),
        ),
    ]
