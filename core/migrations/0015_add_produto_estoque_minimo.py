from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_empresa_plano_os_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="produto",
            name="estoque_minimo",
            field=models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
