from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0016_w0_03_gateway_holding'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='dunningreminder',
            new_name='payments_du_company_266787_idx',
            old_name='pay_dunning_co_sent_idx',
        ),
        migrations.RenameIndex(
            model_name='gatewaypayment',
            new_name='payments_ga_company_7110a7_idx',
            old_name='pay_gp_company_status_idx',
        ),
    ]
