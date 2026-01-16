from django.db import migrations


def migrate_entregue_to_finalizada(apps, schema_editor):
    OrdemServico = apps.get_model("core", "OrdemServico")
    OrdemServico.objects.filter(status="ENTREGUE").update(status="FINALIZADA")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_pagamento_forma_pagamento"),
    ]

    operations = [
        migrations.RunPython(migrate_entregue_to_finalizada, migrations.RunPython.noop),
    ]
