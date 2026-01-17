from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_add_produto_estoque_minimo"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="logomarca",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="empresas/logos/",
                validators=[django.core.validators.FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
            ),
        ),
    ]
