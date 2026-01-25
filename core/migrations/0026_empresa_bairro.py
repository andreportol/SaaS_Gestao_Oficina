from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_empresa_endereco"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="bairro",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
