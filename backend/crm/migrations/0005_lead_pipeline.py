import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0055_os_vision_plan"),
        ("crm", "0004_opportunity_closed_at"),
        ("masters", "0020_customer_pincode"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="source",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="message",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="dedupe_review",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="lead",
            name="dedupe_candidates",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lead",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_leads",
                to="accounts.companyuser",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="dedupe_matched_customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="deduped_leads",
                to="masters.customer",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="dedupe_matched_lead",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dedupe_matches",
                to="crm.lead",
            ),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["company", "source"], name="crm_lead_company_source_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["company", "assigned_to"], name="crm_lead_company_assignee_idx"),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["company", "dedupe_review"], name="crm_lead_company_review_idx"),
        ),
    ]
