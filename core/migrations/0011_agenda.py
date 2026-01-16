from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_alter_produto_estoque_atual"),
    ]

    operations = [
        migrations.CreateModel(
            name="Agenda",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_agendada", models.DateField()),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="agendas", to="core.cliente"
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="agendas", to="core.empresa"
                    ),
                ),
                (
                    "veiculo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="agendamentos", to="core.veiculo"
                    ),
                ),
            ],
            options={
                "ordering": ["-data_agendada", "-id"],
                "unique_together": {("empresa", "cliente", "veiculo", "data_agendada")},
            },
        ),
    ]
