from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cliente, Empresa, OrdemServico, OSItem, Pagamento, Veiculo


User = get_user_model()


class EmpresaIsolationTest(TestCase):
    def setUp(self):
        self.empresa1 = Empresa.objects.create(nome="Oficina 1")
        self.empresa2 = Empresa.objects.create(nome="Oficina 2")
        self.user1 = User.objects.create_user(username="u1", password="123", empresa=self.empresa1)
        self.user2 = User.objects.create_user(username="u2", password="123", empresa=self.empresa2)
        self.cliente1 = Cliente.objects.create(empresa=self.empresa1, nome="Cliente 1", telefone="1111")
        self.cliente2 = Cliente.objects.create(empresa=self.empresa2, nome="Cliente 2", telefone="2222")
        self.veiculo1 = Veiculo.objects.create(
            empresa=self.empresa1,
            cliente=self.cliente1,
            tipo=Veiculo.Tipo.CARRO,
            placa="AAA1234",
            marca="Marca",
            modelo="Modelo",
        )
        self.veiculo2 = Veiculo.objects.create(
            empresa=self.empresa2,
            cliente=self.cliente2,
            tipo=Veiculo.Tipo.CARRO,
            placa="BBB1234",
            marca="Marca",
            modelo="Modelo",
        )
        self.os1 = OrdemServico.objects.create(
            empresa=self.empresa1,
            cliente=self.cliente1,
            veiculo=self.veiculo1,
            problema="Teste",
            entrada_em=timezone.now().date(),
        )
        self.os2 = OrdemServico.objects.create(
            empresa=self.empresa2,
            cliente=self.cliente2,
            veiculo=self.veiculo2,
            problema="Teste",
            entrada_em=timezone.now().date(),
        )

    def test_lista_clientes_filtra_por_empresa(self):
        self.client.force_login(self.user1)
        response = self.client.get(reverse("clientes_list"))
        self.assertContains(response, self.cliente1.nome)
        self.assertNotContains(response, self.cliente2.nome)

    def test_lista_os_filtra_por_empresa(self):
        self.client.force_login(self.user2)
        response = self.client.get(reverse("os_list"))
        self.assertContains(response, str(self.os2.id))
        self.assertNotContains(response, str(self.os1.id))

    def test_calcula_saldo(self):
        OSItem.objects.create(
            empresa=self.empresa1, os=self.os1, descricao="Item", qtd=1, valor_unitario=100, subtotal=100
        )
        Pagamento.objects.create(
            empresa=self.empresa1, os=self.os1, valor=60, forma_pagamento=Pagamento.Metodo.DINHEIRO
        )
        self.assertEqual(self.os1.total, 100)
        self.assertEqual(self.os1.total_pago, 60)
        self.assertEqual(self.os1.saldo, 40)
