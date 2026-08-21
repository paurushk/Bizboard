from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0022_wave17_multi_company_feature_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="InviteJti",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("jti", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invite_jtis",
                        to="accounts.companyuser",
                    ),
                ),
            ],
        ),
    ]
