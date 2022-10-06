# Generated by Django 3.2.15 on 2022-09-27 13:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_ssot", "0002_performance_metrics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="synclogentry",
            name="message",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="synclogentry",
            name="object_repr",
            field=models.TextField(blank=True, default="", editable=False),
        ),
    ]