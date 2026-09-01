from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insights', '0004_a08_shop_floor_events'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopfloorevent',
            options={'ordering': ['-created_at']},
        ),
        migrations.RenameIndex(
            model_name='attentionrowstate',
            new_name='insights_at_company_a71081_idx',
            old_name='insights_at_company_snooze_idx',
        ),
        migrations.RenameIndex(
            model_name='shopfloorevent',
            new_name='insights_sh_company_da213a_idx',
            old_name='ins_shop_co_ev_on_idx',
        ),
        migrations.AlterField(
            model_name='shopfloorevent',
            name='event',
            field=models.CharField(choices=[('invoice_complete', 'Invoice Complete'), ('pos_line_added', 'Pos Line Added'), ('offline_enqueue', 'Offline Enqueue'), ('offline_flush_fail', 'Offline Flush Fail'), ('complete_duration_ms', 'Complete Duration Ms'), ('time_to_first_invoice_ms', 'Time To First Invoice Ms')], db_index=True, max_length=40),
        ),
    ]
