from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0028_usuario_email_recuperacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="telefone_recuperacao",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
