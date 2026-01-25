from django.db import migrations, models


def set_existing_empresas_confirmed(apps, schema_editor):
    Empresa = apps.get_model("core", "Empresa")
    Empresa.objects.filter(pagamento_confirmado=False).update(pagamento_confirmado=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0023_veiculo_km"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="pagamento_confirmado",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(set_existing_empresas_confirmed, migrations.RunPython.noop),
    ]
