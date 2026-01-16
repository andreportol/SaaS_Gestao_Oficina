from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_usuario_managers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="veiculo",
            name="ano",
            field=models.CharField(blank=True, max_length=9, null=True),
        ),
    ]
