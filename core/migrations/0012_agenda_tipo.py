from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_agenda"),
    ]

    operations = [
        migrations.AddField(
            model_name="agenda",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("ENTREGA", "Entrega (deixar)"),
                    ("RETIRADA", "Retirada (buscar)"),
                    ("NOTA", "Anotação"),
                ],
                default="NOTA",
                max_length=20,
            ),
        ),
    ]
