from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_add_cliente_endereco"),
    ]

    operations = [
        migrations.AddField(
            model_name="produto",
            name="descricao",
            field=models.TextField(blank=True),
        ),
    ]
