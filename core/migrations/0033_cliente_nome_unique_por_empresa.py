from django.db import migrations, models
from django.db.models import Count


def _normalizar_e_consolidar_clientes(apps, schema_editor):
    Cliente = apps.get_model("core", "Cliente")
    Veiculo = apps.get_model("core", "Veiculo")
    Agenda = apps.get_model("core", "Agenda")
    OrdemServico = apps.get_model("core", "OrdemServico")

    for cliente in Cliente.objects.all().only("id", "nome"):
        nome = (cliente.nome or "").strip().upper()
        if not nome:
            nome = f"SEM NOME {cliente.id}"
        if cliente.nome != nome:
            Cliente.objects.filter(pk=cliente.pk).update(nome=nome)

    duplicados = (
        Cliente.objects.values("empresa_id", "nome")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )

    for item in duplicados:
        clientes = list(
            Cliente.objects.filter(empresa_id=item["empresa_id"], nome=item["nome"]).order_by("id")
        )
        principal = clientes[0]

        for duplicado in clientes[1:]:
            Veiculo.objects.filter(cliente_id=duplicado.id).update(cliente_id=principal.id)
            OrdemServico.objects.filter(cliente_id=duplicado.id).update(cliente_id=principal.id)

            for agenda in Agenda.objects.filter(cliente_id=duplicado.id).order_by("id"):
                existe_conflito = (
                    Agenda.objects.filter(
                        empresa_id=agenda.empresa_id,
                        cliente_id=principal.id,
                        veiculo_id=agenda.veiculo_id,
                        data_agendada=agenda.data_agendada,
                        hora_agendada=agenda.hora_agendada,
                    )
                    .exclude(pk=agenda.pk)
                    .exists()
                )
                if existe_conflito:
                    agenda.delete()
                else:
                    agenda.cliente_id = principal.id
                    agenda.save(update_fields=["cliente"])

            duplicado.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_plano_valor_pix_fields"),
    ]

    operations = [
        migrations.RunPython(_normalizar_e_consolidar_clientes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cliente",
            constraint=models.UniqueConstraint(fields=("empresa", "nome"), name="uniq_cliente_empresa_nome"),
        ),
    ]
