from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0028_onboarding_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="pan",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="company",
            name="pan_legal_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="pan_raw_payload",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="pan_verification_status",
            field=models.CharField(blank=True, default="UNVERIFIED", max_length=16),
        ),
        migrations.AddField(
            model_name="company",
            name="pan_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="udyam",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="company",
            name="udyam_enterprise_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="udyam_raw_payload",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="udyam_verification_status",
            field=models.CharField(blank=True, default="UNVERIFIED", max_length=16),
        ),
        migrations.AddField(
            model_name="company",
            name="udyam_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
