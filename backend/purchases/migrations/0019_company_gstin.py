import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
        ("purchases", "0018_sprint2_itc_rcm_cess"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoice",
            name="company_gstin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_invoices",
                to="accounts.companygstin",
            ),
        ),
    ]
