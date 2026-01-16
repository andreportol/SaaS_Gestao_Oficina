from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cliente, Empresa, OrdemServico, OSItem, Pagamento, Veiculo
from .permissions import ROLE_EMPLOYEE, ROLE_MANAGER, setup_roles


User = get_user_model()


class EmpresaIsolationTest(TestCase):
    def setUp(self):
        self.empresa1 = Empresa.objects.create(nome="Oficina 1")
        self.empresa2 = Empresa.objects.create(nome="Oficina 2")
        self.user1 = User.objects.create_user(username="u1", password="123", empresa=self.empresa1)
        self.user2 = User.objects.create_user(username="u2", password="123", empresa=self.empresa2)
        self.user2.is_manager = True
        self.user2.save(update_fields=["is_manager"])
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
            responsavel=self.user2,
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


class UserManagementTests(TestCase):
    def setUp(self):
        setup_roles()
        self.empresa = Empresa.objects.create(nome="Oficina X")
        self.manager = User.objects.create_user(
            username="manager", password="123", empresa=self.empresa, is_manager=True
        )
        gerente_group = Group.objects.get(name=ROLE_MANAGER)
        self.manager.groups.add(gerente_group)
        self.employee = User.objects.create_user(username="employee", password="123", empresa=self.empresa)
        funcionario_group = Group.objects.get(name=ROLE_EMPLOYEE)
        self.employee.groups.add(funcionario_group)

    def test_manager_cria_usuario_ate_limite(self):
        self.client.force_login(self.manager)
        url = reverse("usuarios_create")
        for i in range(5):
            payload = {
                "username": f"user{i}",
                "email": f"user{i}@test.com",
                "first_name": "User",
                "last_name": f"{i}",
                "is_active": "on",
                "password1": "Senha12345!",
                "password2": "Senha12345!",
            }
            response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.filter(empresa=self.empresa, is_active=True).count(), 6)

        response = self.client.post(
            url,
            {
                "username": "extra",
                "email": "extra@test.com",
                "first_name": "Extra",
                "last_name": "User",
                "is_active": "on",
                "password1": "Senha12345!",
                "password2": "Senha12345!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Limite de usuarios ativos atingido")

    def test_funcionario_recebe_403_em_usuarios(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("usuarios_list"))
        self.assertEqual(response.status_code, 403)

    def test_funcionario_sem_delete_permission(self):
        self.assertFalse(self.employee.has_perm("core.delete_cliente"))

    def test_os_queryset_funcionario(self):
        cliente = Cliente.objects.create(empresa=self.empresa, nome="Cliente", telefone="0000")
        veiculo = Veiculo.objects.create(
            empresa=self.empresa,
            cliente=cliente,
            tipo=Veiculo.Tipo.CARRO,
            placa="AAA0000",
            marca="Marca",
            modelo="Modelo",
        )
        os1 = OrdemServico.objects.create(
            empresa=self.empresa,
            cliente=cliente,
            veiculo=veiculo,
            responsavel=self.employee,
            problema="Teste 1",
            entrada_em=timezone.now().date(),
        )
        os2 = OrdemServico.objects.create(
            empresa=self.empresa,
            cliente=cliente,
            veiculo=veiculo,
            responsavel=self.manager,
            problema="Teste 2",
            entrada_em=timezone.now().date(),
        )

        self.client.force_login(self.employee)
        response = self.client.get(reverse("os_list"))
        self.assertContains(response, str(os1.id))
        self.assertNotContains(response, str(os2.id))
