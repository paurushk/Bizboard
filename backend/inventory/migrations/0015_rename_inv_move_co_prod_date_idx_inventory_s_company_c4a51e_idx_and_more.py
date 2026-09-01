from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_w0_06_running_cost'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='stockmovement',
            new_name='inventory_s_company_c4a51e_idx',
            old_name='inv_move_co_prod_date_idx',
        ),
        migrations.RenameIndex(
            model_name='stockmovement',
            new_name='inventory_s_company_381299_idx',
            old_name='inv_move_co_wh_prod_date_idx',
        ),
    ]
