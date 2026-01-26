from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0029_usuario_telefone_recuperacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="renovacao_periodo",
            field=models.CharField(blank=True, default="", max_length=3, choices=[("30d", "30 dias"), ("6m", "6 meses"), ("12m", "12 meses")]),
        ),
        migrations.AddField(
            model_name="empresa",
            name="renovacao_solicitada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
