from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0031_plano_valor"),
    ]

    operations = [
        migrations.AddField(
            model_name="planovalor",
            name="pix_qr_code",
            field=models.ImageField(blank=True, null=True, upload_to="planos/qrcode/"),
        ),
        migrations.AddField(
            model_name="planovalor",
            name="pix_copia_cola",
            field=models.TextField(blank=True, default=""),
        ),
    ]
