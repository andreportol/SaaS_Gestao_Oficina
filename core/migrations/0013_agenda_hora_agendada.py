from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_agenda_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="agenda",
            name="hora_agendada",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="agenda",
            options={"ordering": ["-data_agendada", "-hora_agendada", "-id"]},
        ),
        migrations.AlterUniqueTogether(
            name="agenda",
            unique_together={("empresa", "cliente", "veiculo", "data_agendada", "hora_agendada")},
        ),
    ]
