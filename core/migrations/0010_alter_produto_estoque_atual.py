from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_add_produto_descricao"),
    ]

    operations = [
        migrations.AlterField(
            model_name="produto",
            name="estoque_atual",
            field=models.IntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
