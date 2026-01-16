from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_agenda_hora_agendada"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="plano",
            field=models.CharField(
                choices=[("BASICO", "Basico"), ("PLUS", "Plus")],
                default="BASICO",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="criado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="os_criadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="finalizado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="finalizado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="os_finalizadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="iniciado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ordemservico",
            name="responsavel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="os_responsavel",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="OrdemServicoLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "acao",
                    models.CharField(
                        choices=[
                            ("CRIAR", "Criar"),
                            ("ATRIBUIR", "Atribuir"),
                            ("INICIAR", "Iniciar"),
                            ("FINALIZAR", "Finalizar"),
                            ("CANCELAR", "Cancelar"),
                            ("EDITAR", "Editar"),
                        ],
                        max_length=30,
                    ),
                ),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="os_logs", to="core.empresa"
                    ),
                ),
                (
                    "os",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="core.ordemservico",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-criado_em", "-id"]},
        ),
    ]
