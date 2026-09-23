import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0055_os_vision_plan"),
        ("insights", "0008_shopfloorevent_journey_envelope"),
    ]

    operations = [
        migrations.AddField(
            model_name="attentionrowstate",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_attention_rows",
                to="accounts.companyuser",
            ),
        ),
        migrations.AddField(
            model_name="attentionrowstate",
            name="due_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="attentionrowstate",
            index=models.Index(fields=["company", "assigned_to"], name="attn_company_assignee_idx"),
        ),
    ]
