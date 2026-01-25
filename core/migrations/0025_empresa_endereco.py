from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_empresa_pagamento_confirmado"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="cep",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="empresa",
            name="rua",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="empresa",
            name="numero",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cidade",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
