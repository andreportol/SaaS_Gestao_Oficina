from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cliente, Despesa, Empresa, OrdemServico, OSItem, Pagamento, Veiculo
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
        self.assertContains(response, f"<td>{self.os2.id}</td>")
        self.assertNotContains(response, f"<td>{self.os1.id}</td>")

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
        for i in range(4):
            payload = {
                "username": f"user{i}",
                "email": f"user{i}@test.com",
                "first_name": "User",
                "last_name": f"{i}",
                "is_active": "True",
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
                "is_active": "True",
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
        self.assertContains(response, f"<td>{os1.id}</td>")
        self.assertNotContains(response, f"<td>{os2.id}</td>")


class DashboardDataTests(TestCase):
    def setUp(self):
        self.empresa1 = Empresa.objects.create(nome="Empresa 1")
        self.empresa2 = Empresa.objects.create(nome="Empresa 2")
        self.manager = User.objects.create_user(
            username="manager", password="123", empresa=self.empresa1, is_manager=True
        )
        self.employee = User.objects.create_user(username="employee", password="123", empresa=self.empresa1)
        self.other_user = User.objects.create_user(username="other", password="123", empresa=self.empresa2)
        self.cliente1 = Cliente.objects.create(empresa=self.empresa1, nome="Cliente 1", telefone="1111")
        self.cliente2 = Cliente.objects.create(empresa=self.empresa2, nome="Cliente 2", telefone="2222")
        self.veiculo1 = Veiculo.objects.create(
            empresa=self.empresa1,
            cliente=self.cliente1,
            tipo=Veiculo.Tipo.CARRO,
            placa="AAA1111",
            marca="Marca",
            modelo="Modelo",
        )
        self.veiculo2 = Veiculo.objects.create(
            empresa=self.empresa2,
            cliente=self.cliente2,
            tipo=Veiculo.Tipo.CARRO,
            placa="BBB2222",
            marca="Marca",
            modelo="Modelo",
        )
        self.os_employee = OrdemServico.objects.create(
            empresa=self.empresa1,
            cliente=self.cliente1,
            veiculo=self.veiculo1,
            responsavel=self.employee,
            problema="Teste",
            entrada_em=timezone.now().date(),
        )
        self.os_manager = OrdemServico.objects.create(
            empresa=self.empresa1,
            cliente=self.cliente1,
            veiculo=self.veiculo1,
            responsavel=self.manager,
            problema="Teste",
            entrada_em=timezone.now().date(),
        )
        self.os_other = OrdemServico.objects.create(
            empresa=self.empresa2,
            cliente=self.cliente2,
            veiculo=self.veiculo2,
            responsavel=self.other_user,
            problema="Teste",
            entrada_em=timezone.now().date(),
        )
        Pagamento.objects.create(
            empresa=self.empresa1,
            os=self.os_employee,
            valor=100,
            forma_pagamento=Pagamento.Metodo.DINHEIRO,
        )
        Pagamento.objects.create(
            empresa=self.empresa1,
            os=self.os_manager,
            valor=200,
            forma_pagamento=Pagamento.Metodo.DINHEIRO,
        )
        Pagamento.objects.create(
            empresa=self.empresa2,
            os=self.os_other,
            valor=999,
            forma_pagamento=Pagamento.Metodo.DINHEIRO,
        )
        Despesa.objects.create(empresa=self.empresa1, descricao="Despesa", valor=50)

    def test_dashboard_data_funcionario_filtra_os_e_pagamentos(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("dashboard_data"), {"range": "30d"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(sum(data["operacional"]["os_por_funcionario"]["valores"]), 1)
        self.assertEqual(data["financeiro"]["saldo_geral"], 50.0)

    def test_dashboard_data_gerente_enxerga_empresa(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("dashboard_data"), {"range": "30d"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(sum(data["operacional"]["os_por_funcionario"]["valores"]), 2)
        self.assertEqual(data["financeiro"]["saldo_geral"], 250.0)
