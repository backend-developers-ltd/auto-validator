# Generated by Django 4.2.15 on 2024-09-05 01:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_alter_subnet_operators"),
    ]

    operations = [
        migrations.AlterField(
            model_name="validatorinstance",
            name="server",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT, related_name="validator_instances", to="core.server"
            ),
        ),
        migrations.AlterField(
            model_name="validatorinstance",
            name="subnet_slot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="validator_instances", to="core.subnetslot"
            ),
        ),
    ]
