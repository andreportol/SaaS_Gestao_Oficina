from django.db import migrations, models


def normalize_forma_pagamento(apps, schema_editor):
    Pagamento = apps.get_model("core", "Pagamento")
    valid = {
        "Cartão de Débito",
        "Cartão de Crédito",
        "Dinheiro",
        "PIX",
        "Cheque",
        "Outro",
    }
    for pagamento in Pagamento.objects.all():
        if pagamento.forma_pagamento not in valid:
            pagamento.forma_pagamento = "Outro"
            pagamento.save(update_fields=["forma_pagamento"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_alter_veiculo_ano"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pagamento",
            name="forma_pagamento",
            field=models.CharField(
                choices=[
                    ("Cartão de Débito", "Cartão de Débito"),
                    ("Cartão de Crédito", "Cartão de Crédito"),
                    ("Dinheiro", "Dinheiro"),
                    ("PIX", "PIX"),
                    ("Cheque", "Cheque"),
                    ("Outro", "Outro"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(normalize_forma_pagamento, migrations.RunPython.noop),
    ]
