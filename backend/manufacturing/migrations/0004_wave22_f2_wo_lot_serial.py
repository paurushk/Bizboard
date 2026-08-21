from django.db import migrations, models

import django.db.models.deletion





class Migration(migrations.Migration):



    dependencies = [

        ("inventory", "0008_partial_closures"),

        ("manufacturing", "0003_wave22_wo_business_dates"),

    ]



    operations = [

        migrations.AddField(

            model_name="workorder",

            name="serial_numbers",

            field=models.JSONField(blank=True, default=list),

        ),

        migrations.AddField(

            model_name="workorderline",

            name="batch",

            field=models.ForeignKey(

                blank=True,

                null=True,

                on_delete=django.db.models.deletion.PROTECT,

                related_name="+",

                to="inventory.batchlot",

            ),

        ),

        migrations.AddField(

            model_name="workorderline",

            name="lot_allocations",

            field=models.JSONField(blank=True, default=list),

        ),

    ]


