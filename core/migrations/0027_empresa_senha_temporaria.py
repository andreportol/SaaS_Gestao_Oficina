from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_empresa_bairro"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="senha_temporaria",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
