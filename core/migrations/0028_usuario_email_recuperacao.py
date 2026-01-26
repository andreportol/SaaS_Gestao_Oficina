from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0027_empresa_senha_temporaria"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="email_recuperacao",
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
