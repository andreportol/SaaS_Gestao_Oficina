from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Cliente, Empresa, OrdemServico, OSItem, Pagamento, Usuario, Veiculo


class Command(BaseCommand):
    help = "Cria dados de demonstração (empresa, usuário admin, clientes e OS)."

    def handle(self, *args, **options):
        empresa, _ = Empresa.objects.get_or_create(nome="Oficina Demo", defaults={"telefone": "11999999999"})
        user, created = Usuario.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@demo.com",
                "empresa": empresa,
                "is_staff": True,
                "is_superuser": True,
                "is_manager": True,
            },
        )
        if created:
            user.set_password("admin123")
            user.save()

        cliente, _ = Cliente.objects.get_or_create(
            empresa=empresa, nome="Cliente Demo", telefone="11988887777", email="cliente@demo.com"
        )
        veiculo, _ = Veiculo.objects.get_or_create(
            empresa=empresa,
            cliente=cliente,
            placa="ABC1D23",
            defaults={"tipo": Veiculo.Tipo.CARRO, "marca": "Fiat", "modelo": "Uno", "ano": 2010},
        )
        os, _ = OrdemServico.objects.get_or_create(
            empresa=empresa,
            cliente=cliente,
            veiculo=veiculo,
            problema="Troca de óleo e revisão.",
            defaults={
                "status": OrdemServico.Status.ABERTA,
                "entrada_em": timezone.now().date(),
                "mao_de_obra": 150,
                "desconto": 0,
            },
        )
        OSItem.objects.get_or_create(
            empresa=empresa,
            os=os,
            descricao="Óleo 5W30",
            defaults={"qtd": 1, "valor_unitario": 90, "subtotal": 90},
        )
        Pagamento.objects.get_or_create(
            empresa=empresa,
            os=os,
            valor=100,
            forma_pagamento=Pagamento.Metodo.DINHEIRO,
            defaults={"pago_em": timezone.now().date()},
        )

        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados."))
        self.stdout.write(self.style.SUCCESS("Usuário: admin / Senha: admin123"))
