from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0010_d04_chase'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='gstr2bingest',
            new_name='reporting_g_company_3215ab_idx',
            old_name='reporting_g_company_ims_idx',
        ),
        migrations.RenameIndex(
            model_name='imsactionhistory',
            new_name='reporting_i_company_87754e_idx',
            old_name='reporting_i_company_ingest_idx',
        ),
        migrations.AlterField(
            model_name='gstr2bingest',
            name='chase_status',
            field=models.CharField(choices=[('none', 'None'), ('requested', 'Requested'), ('received', 'Received'), ('imported', 'Imported'), ('matched', 'Matched')], db_index=True, default='none', max_length=16),
        ),
        migrations.AlterField(
            model_name='gstr2bingest',
            name='ims_action',
            field=models.CharField(choices=[('NO_ACTION', 'No Action'), ('ACCEPT', 'Accept'), ('REJECT', 'Reject'), ('PENDING', 'Pending')], db_index=True, default='NO_ACTION', max_length=16),
        ),
        migrations.AlterField(
            model_name='gstr2bingest',
            name='match_class',
            field=models.CharField(blank=True, choices=[('exact', 'Exact'), ('value_mismatch', 'Value Mismatch'), ('missing_in_books', 'Missing In Books'), ('missing_in_ims', 'Missing In Ims'), ('wrong_gstin', 'Wrong Gstin'), ('duplicate', 'Duplicate'), ('potentially_ineligible', 'Potentially Ineligible'), ('other', 'Other')], default='', max_length=32),
        ),
    ]
