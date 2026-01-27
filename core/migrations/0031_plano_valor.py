from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0030_empresa_renovacao_periodo"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanoValor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plano", models.CharField(choices=[("BASICO", "Basico"), ("PLUS", "Plus")], max_length=10)),
                ("periodo", models.CharField(choices=[("30d", "30 dias"), ("6m", "6 meses"), ("12m", "12 meses")], max_length=3)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Valor do plano",
                "verbose_name_plural": "Valores do plano",
                "ordering": ("plano", "periodo"),
                "unique_together": {("plano", "periodo")},
            },
        ),
    ]
