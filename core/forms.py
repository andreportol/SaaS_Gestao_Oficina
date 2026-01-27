import json
import logging
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import password_validators_help_texts, validate_password
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import (
    Agenda,
    Cliente,
    Despesa,
    Empresa,
    Funcionario,
    OrdemServico,
    OSItem,
    Pagamento,
    Produto,
    Veiculo,
)
from .permissions import ROLE_EMPLOYEE, ROLE_MANAGER


User = get_user_model()
logger = logging.getLogger(__name__)


def _coerce_display_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _digits_only(value):
    return re.sub(r"\D", "", value or "")


def _is_valid_cpf(digits):
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    total = sum(int(d) * weight for d, weight in zip(digits[:9], range(10, 1, -1)))
    first = (total * 10) % 11
    first = 0 if first == 10 else first
    if first != int(digits[9]):
        return False
    total = sum(int(d) * weight for d, weight in zip(digits[:10], range(11, 1, -1)))
    second = (total * 10) % 11
    second = 0 if second == 10 else second
    return second == int(digits[10])


def _is_valid_cnpj(digits):
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:12], weights_first))
    mod = total % 11
    first = 0 if mod < 2 else 11 - mod
    if first != int(digits[12]):
        return False
    total = sum(int(d) * w for d, w in zip(digits[:13], weights_second))
    mod = total % 11
    second = 0 if mod < 2 else 11 - mod
    return second == int(digits[13])


def _validate_cnpj_cpf(value):
    digits = _digits_only(value)
    if not digits:
        return ""
    if len(digits) == 11:
        if not _is_valid_cpf(digits):
            raise forms.ValidationError("CPF inválido.")
        return digits
    if len(digits) == 14:
        if not _is_valid_cnpj(digits):
            raise forms.ValidationError("CNPJ inválido.")
        return digits
    raise forms.ValidationError("Informe CPF (11 dígitos) ou CNPJ (14 dígitos).")


def _send_resend_email(subject, body, to_email, reply_to=None):
    api_key = getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        return False, "RESEND_API_KEY nao configurada."
    from_email = getattr(settings, "EMAIL_FROM", "no-reply@alpsistemas.app")
    api_url = "https://api.resend.com/emails"

    def _send_payload(sender):
        payload = {
            "from": sender,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            return True

    def _parse_resend_error(exc):
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            return payload.get("message") or payload.get("error") or payload.get("statusText")
        except Exception:
            return None

    try:
        _send_payload(from_email)
    except urllib.error.HTTPError as exc:
        if settings.DEBUG:
            test_from = getattr(settings, "RESEND_TEST_FROM_EMAIL", "")
            if test_from and test_from != from_email:
                try:
                    _send_payload(test_from)
                    return True, None
                except urllib.error.HTTPError as retry_exc:
                    exc = retry_exc
        detail = _parse_resend_error(exc)
        logger.warning("Resend email failed: %s", detail or f"HTTP {exc.code}")
        return False, detail or f"HTTP {exc.code}"
    except Exception:
        logger.exception("Resend email failed")
        return False, "Erro de comunicacao com o servico de email."

    return True, None


def _notify_nova_liberacao(empresa, user):
    to_email = getattr(settings, "CONTACT_EMAIL", "alpsistemascg@gmail.com")
    nome_responsavel = user.get_full_name() or user.username
    subject = "Nova solicitacao de liberacao de acesso"
    body = (
        "Solicitação de liberação de acesso ao SaaS Gestão de Oficina.\n\n"
        f"Empresa: {empresa.nome}\n"
        f"Responsavel: {nome_responsavel}\n"
        f"Email: {user.email or '-'}\n"
        f"Telefone: {empresa.telefone or '-'}\n"
        f"CNPJ/CPF: {empresa.cnpj_cpf or '-'}\n"
    )
    return _send_resend_email(subject, body, to_email, reply_to=user.email or None)


def _notify_aprovacao_acesso(empresa, user, senha):
    if not user.email:
        return False, "Usuario sem email cadastrado."
    subject = "Acesso liberado - SaaS Gestão de Oficina"
    body = (
        "Seu acesso ao SaaS Gestão de Oficina foi liberado.\n\n"
        f"Login: {user.username}\n"
        f"Senha: {senha}\n"
        f"Empresa: {empresa.nome}\n"
    )
    return _send_resend_email(subject, body, user.email)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        username = self.fields.get("username")
        if username:
            username.widget.attrs.setdefault("autofocus", "autofocus")
        password = self.fields.get("password")
        if password:
            password.widget.attrs.setdefault("autocomplete", "current-password")


class EmpresaFormMixin(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self._filtrar_por_empresa()

    def _filtrar_por_empresa(self):
        empresa = getattr(self.user, "empresa", None)
        if not empresa:
            return
        for name, field in self.fields.items():
            if hasattr(field, "queryset") and isinstance(field.queryset, models.QuerySet):
                model = field.queryset.model
                if hasattr(model, "empresa"):
                    self.fields[name].queryset = field.queryset.filter(empresa=empresa)
                if name == "veiculo":
                    # sempre traz veículos da empresa; filtragem por cliente fica no JS
                    self.fields[name].queryset = Veiculo.objects.filter(empresa=empresa)


class ClienteForm(EmpresaFormMixin):
    data_cadastro = forms.DateField(
        label="Data de cadastro",
        required=False,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "form-control",
                "placeholder": "dd/mm/aaaa",
                "inputmode": "numeric",
                "data-date-picker": "br",
                "autocomplete": "off",
            },
        ),
    )

    class Meta:
        model = Cliente
        fields = ["nome", "telefone", "email", "documento", "cep", "rua", "numero", "bairro", "cidade"]
        widgets = {
            "telefone": forms.TextInput(attrs={"placeholder": "(99)99999-9999", "data-mask": "phone"}),
            "documento": forms.TextInput(
                attrs={"placeholder": "000.000.000-00", "data-mask": "cpf", "inputmode": "numeric"}
            ),
            "cep": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "data-mask": "cep",
                    "inputmode": "numeric",
                    "data-lookup": "viacep",
                }
            ),
            "rua": forms.TextInput(attrs={"placeholder": "Logradouro"}),
            "numero": forms.TextInput(attrs={"placeholder": "Número"}),
            "bairro": forms.TextInput(attrs={"placeholder": "Bairro"}),
            "cidade": forms.TextInput(attrs={"placeholder": "Cidade"}),
        }
        labels = {"documento": "CPF", "cep": "CEP", "rua": "Logradouro"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        created_at = _coerce_display_date(getattr(self.instance, "criado_em", None))
        if not created_at:
            created_at = _coerce_display_date(timezone.now())
        self.initial.setdefault("data_cadastro", created_at)
        if "data_cadastro" in self.fields:
            self.fields["data_cadastro"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
            self.fields["data_cadastro"].disabled = True
        self.order_fields(
            ["nome", "telefone", "email", "documento", "cep", "rua", "numero", "bairro", "cidade", "data_cadastro"]
        )


class VeiculoForm(EmpresaFormMixin):
    data_cadastro = forms.DateField(
        label="Data de cadastro",
        required=False,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "form-control",
                "placeholder": "dd/mm/aaaa",
                "inputmode": "numeric",
                "data-date-picker": "br",
                "autocomplete": "off",
            },
        ),
    )

    BRANDS_BY_TIPO = {
        Veiculo.Tipo.CARRO: [
            "Aston Martin",
            "Audi",
            "Bentley",
            "BMW",
            "BYD",
            "Caoa Chery",
            "Chevrolet",
            "Citroën",
            "Fiat",
            "Ford",
            "GWM / Haval",
            "Honda",
            "Hyundai",
            "Jeep",
            "Kia",
            "Land Rover / Jaguar",
            "Lexus",
            "Mini",
            "Mitsubishi",
            "Nissan",
            "Peugeot",
            "Renault",
            "Suzuki",
            "Toyota",
            "Volkswagen",
            "Volvo",
        ],
        Veiculo.Tipo.MOTO: [
            "Avelloz",
            "Bajaj",
            "BMW",
            "BMW Motorrad",
            "Dafra",
            "Ducati",
            "Haojue",
            "Harley-Davidson",
            "Honda",
            "Kawasaki",
            "KTM",
            "Mottu",
            "Royal Enfield",
            "Shineray",
            "Suzuki",
            "Tailg",
            "Triumph",
            "Voltz Motors",
            "Watts",
            "Yamaha",
        ],
        Veiculo.Tipo.CAMINHAO: ["Volvo", "Scania", "Mercedes-Benz", "Volkswagen", "Iveco", "DAF", "MAN", "Ford"],
    }

    class Meta:
        model = Veiculo
        fields = ["cliente", "tipo", "marca", "modelo", "ano", "cor", "placa", "km"]
        widgets = {
            "placa": forms.TextInput(attrs={"placeholder": "ABC1D23", "style": "text-transform: uppercase;"}),
            "ano": forms.TextInput(
                attrs={"placeholder": "2023/2024", "data-mask": "ano-modelo", "inputmode": "numeric"}
            ),
            "modelo": forms.TextInput(attrs={"placeholder": "Onix Plus"}),
            "km": forms.NumberInput(attrs={"min": "0", "step": "1", "placeholder": "Quilometragem"}),
        }
        labels = {"ano": "Ano/Modelo", "km": "Quilometragem (km)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        marcas_set = {marca for marcas in self.BRANDS_BY_TIPO.values() for marca in marcas}
        current = self.initial.get("marca") or getattr(self.instance, "marca", "") or self.data.get("marca")
        if current:
            marcas_set.add(current)
        marcas = sorted(marcas_set)
        self.fields["marca"].widget = forms.TextInput(
            attrs={
                "list": "marca-options",
                "placeholder": "Digite ou selecione a marca",
                "data-brands": json.dumps(self.BRANDS_BY_TIPO),
                "data-placeholder": "Digite ou selecione a marca",
            }
        )
        # Keep current value available via datalist without enforcing choices server-side
        self.fields["marca"].initial = current or ""

        if self.instance and self.instance.pk:
            self.fields.pop("data_cadastro", None)
        if "data_cadastro" in self.fields:
            self.initial.setdefault("data_cadastro", _coerce_display_date(timezone.now()))
            self.fields["data_cadastro"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
            self.fields["data_cadastro"].disabled = True
        order = ["cliente", "tipo", "marca", "modelo", "ano", "cor", "placa", "km"]
        if "data_cadastro" in self.fields:
            order.append("data_cadastro")
        self.order_fields(order)

    def clean_marca(self):
        marca = (self.cleaned_data.get("marca") or "").strip()
        return marca

    def clean_ano(self):
        ano = (self.cleaned_data.get("ano") or "").strip()
        if not ano:
            return ""

        digits = re.sub(r"\D", "", ano)
        if len(digits) == 4:
            return digits
        if len(digits) == 8:
            return f"{digits[:4]}/{digits[4:]}"
        raise forms.ValidationError("Informe o ano/modelo no formato 0000/0000.")

    def clean_placa(self):
        placa = (self.cleaned_data.get("placa") or "").strip().upper()
        return placa

    def clean_modelo(self):
        modelo = (self.cleaned_data.get("modelo") or "").strip()
        if not modelo:
            return ""
        words = [w.capitalize() for w in modelo.split()]
        return " ".join(words)

    def clean_cor(self):
        cor = (self.cleaned_data.get("cor") or "").strip()
        if not cor:
            return ""
        words = [w.capitalize() for w in cor.split()]
        return " ".join(words)

    def clean_cep(self):
        cep = (self.cleaned_data.get("cep") or "").strip().upper()
        digits = re.sub(r"\D", "", cep)
        if not digits:
            return ""
        if len(digits) != 8:
            raise forms.ValidationError("CEP deve ter 8 dígitos.")
        return f"{digits[:5]}-{digits[5:]}"


class ProdutoForm(EmpresaFormMixin):
    data_cadastro = forms.DateField(
        label="Data de cadastro",
        required=False,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "form-control",
                "placeholder": "dd/mm/aaaa",
                "inputmode": "numeric",
                "data-date-picker": "br",
                "autocomplete": "off",
            },
        ),
    )

    class Meta:
        model = Produto
        fields = ["nome", "descricao", "codigo", "custo", "preco", "estoque_atual", "estoque_minimo"]
        labels = {"codigo": "Código", "preco": "Preço", "descricao": "Descrição"}
        widgets = {
            "custo": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
            "preco": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
            "descricao": forms.Textarea(attrs={"rows": 2}),
            "estoque_atual": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "estoque_minimo": forms.NumberInput(attrs={"min": "0", "step": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields.pop("data_cadastro", None)
        if "data_cadastro" in self.fields:
            self.initial.setdefault("data_cadastro", _coerce_display_date(timezone.now()))
            self.fields["data_cadastro"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
            self.fields["data_cadastro"].disabled = True
        order = ["nome", "descricao", "codigo", "custo", "preco", "estoque_atual", "estoque_minimo"]
        if "data_cadastro" in self.fields:
            order.append("data_cadastro")
        self.order_fields(order)


class AgendaForm(EmpresaFormMixin):
    class Meta:
        model = Agenda
        fields = ["cliente", "veiculo", "data_agendada", "hora_agendada", "tipo", "observacoes"]
        labels = {
            "data_agendada": "Data",
            "hora_agendada": "Hora",
            "tipo": "Tipo",
            "veiculo": "Veículo",
            "observacoes": "Observações",
        }
        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "veiculo": forms.Select(attrs={"class": "form-select", "data-client-filter": "1"}),
            "data_agendada": forms.DateInput(
                format="%d/%m/%Y",
                attrs={
                    "class": "form-control",
                    "placeholder": "dd/mm/aaaa",
                    "inputmode": "numeric",
                    "data-date-picker": "br",
                    "autocomplete": "off",
                },
            ),
            "hora_agendada": forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "data_agendada" in self.fields:
            self.fields["data_agendada"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")
        veiculo = cleaned.get("veiculo")
        if cliente and veiculo and veiculo.cliente_id != cliente.id:
            self.add_error("veiculo", "Selecione um veículo do cliente escolhido.")
        return cleaned


class OrdemServicoForm(EmpresaFormMixin):
    class Meta:
        model = OrdemServico
        fields = [
            "cliente",
            "veiculo",
            "executor",
            "status",
            "entrada_em",
            "previsao_entrega",
            "problema",
            "diagnostico",
            "mao_de_obra",
            "desconto",
            "observacoes",
        ]
        widgets = {
            "entrada_em": forms.DateInput(
                format="%d/%m/%Y",
                attrs={
                    "placeholder": "dd/mm/aaaa",
                    "inputmode": "numeric",
                    "data-date-picker": "br",
                    "autocomplete": "off",
                },
            ),
            "previsao_entrega": forms.DateInput(
                format="%d/%m/%Y",
                attrs={
                    "placeholder": "dd/mm/aaaa",
                    "inputmode": "numeric",
                    "data-date-picker": "br",
                    "autocomplete": "off",
                },
            ),
            "veiculo": forms.Select(attrs={"data-placeholder": "Selecione o veículo do cliente"}),
            "mao_de_obra": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
            "desconto": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
            "observacoes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }
        labels = {
            "mao_de_obra": "Mão de obra",
            "observacoes": "Observações",
            "desconto": "Desconto em Reais (R$)",
            "previsao_entrega": "Previsão de entrega",
            "executor": "Executor do serviço",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self, "user", None)
        empresa = getattr(user, "empresa", None)

        if "responsavel" in self.fields:
            responsaveis_qs = User.objects.all()
            if empresa:
                responsaveis_qs = responsaveis_qs.filter(empresa=empresa, is_active=True)
            is_manager = getattr(user, "is_gerente", None)
            if callable(is_manager):
                is_manager = is_manager()
            if user and not is_manager:
                responsaveis_qs = responsaveis_qs.filter(pk=user.pk)
                self.fields["responsavel"].disabled = True
                self.fields["responsavel"].initial = user.pk
            self.fields["responsavel"].queryset = responsaveis_qs

        if "executor" in self.fields:
            self.fields["executor"].queryset = self.fields["executor"].queryset.filter(ativo=True)

        veiculos_qs = Veiculo.objects.all()
        if empresa:
            veiculos_qs = veiculos_qs.filter(empresa=empresa)

        cliente_id = self.data.get("cliente") or self.initial.get("cliente") or getattr(self.instance, "cliente_id", None)
        if cliente_id:
            self.fields["veiculo"].queryset = veiculos_qs.filter(cliente_id=cliente_id)
        else:
            self.fields["veiculo"].queryset = veiculos_qs.none()

        vehicles_map = {}
        for v in veiculos_qs:
            vehicles_map.setdefault(v.cliente_id, []).append({"id": v.id, "label": str(v)})
        self.fields["veiculo"].widget.attrs["data-vehicles"] = json.dumps(vehicles_map)

        if not self.instance.pk and not self.data:
            self.initial["mao_de_obra"] = ""

        date_formats = ["%d/%m/%Y", "%Y-%m-%d"]
        for name in ("entrada_em", "previsao_entrega"):
            if name in self.fields:
                self.fields[name].input_formats = date_formats

    def clean_anexo(self):
        anexo = self.cleaned_data.get("anexo")
        if anexo and anexo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Arquivo maior que 5MB não é permitido.")
        return anexo


class OSItemForm(EmpresaFormMixin):
    class Meta:
        model = OSItem
        fields = ["produto", "descricao", "qtd", "valor_unitario"]
        labels = {"descricao": "Descrição"}
        widgets = {
            "produto": forms.Select(attrs={"class": "form-control form-control-sm"}),
            "descricao": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "qtd": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0", "step": "1"}),
            "valor_unitario": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": "0", "step": "0.01"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        produto = cleaned.get("produto")
        qtd = cleaned.get("qtd")
        if produto and qtd is not None:
            estoque = produto.estoque_atual
            if estoque is None:
                self.add_error("produto", "Defina o estoque do produto antes de lançar.")
            else:
                if qtd % Decimal("1") != 0:
                    self.add_error("qtd", "Informe quantidade inteira.")
                elif qtd > estoque:
                    self.add_error("qtd", f"Quantidade acima do estoque disponível ({estoque}).")
        return cleaned


class PagamentoForm(EmpresaFormMixin):
    class Meta:
        model = Pagamento
        fields = ["forma_pagamento", "valor", "pago_em"]
        widgets = {
            "pago_em": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "dd/mm/aaaa",
                    "inputmode": "numeric",
                    "data-date-picker": "br",
                    "autocomplete": "off",
                }
            ),
            "forma_pagamento": forms.Select(attrs={"class": "form-control form-control-sm"}),
            "valor": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "0,00",
                    "inputmode": "decimal",
                    "data-format": "currency2",
                    "data-format-live": "true",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "forma_pagamento" in self.fields:
            self.fields["forma_pagamento"].choices = Pagamento.Metodo.choices
        if not self.initial.get("pago_em"):
            self.initial["pago_em"] = timezone.now().date()
        if "pago_em" in self.fields:
            self.fields["pago_em"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
            initial = self.initial.get("pago_em")
            if isinstance(initial, (datetime, date)):
                self.initial["pago_em"] = initial.strftime("%d/%m/%Y")


class DespesaForm(EmpresaFormMixin):
    class Meta:
        model = Despesa
        fields = ["descricao", "valor", "data"]
        widgets = {
            "data": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "valor": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
        }


class FuncionarioForm(EmpresaFormMixin):
    class Meta:
        model = Funcionario
        fields = ["nome", "telefone", "email", "data_ingresso", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": "autofocus"}),
            "telefone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "(99)99999-9999", "data-mask": "phone"}
            ),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@empresa.com"}),
            "data_ingresso": forms.DateInput(
                format="%d/%m/%Y",
                attrs={
                    "class": "form-control",
                    "placeholder": "dd/mm/aaaa",
                    "inputmode": "numeric",
                    "data-date-picker": "br",
                    "autocomplete": "off",
                },
            ),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {"ativo": "Ativo", "data_ingresso": "Data de ingresso na empresa"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("data_ingresso"):
            ingresso = _coerce_display_date(getattr(self.instance, "data_ingresso", None))
            self.initial["data_ingresso"] = ingresso or _coerce_display_date(timezone.now())
        if "data_ingresso" in self.fields:
            self.fields["data_ingresso"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]


class EmpresaUpdateForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nome", "cnpj_cpf", "telefone", "cep", "rua", "numero", "bairro", "cidade", "logomarca"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": "autofocus"}),
            "cnpj_cpf": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "CNPJ ou CPF",
                    "data-mask": "cnpj-cpf",
                    "inputmode": "numeric",
                }
            ),
            "telefone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "(99)99999-9999", "data-mask": "phone"}
            ),
            "cep": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "00000-000",
                    "data-mask": "cep",
                    "inputmode": "numeric",
                    "data-lookup": "viacep",
                }
            ),
            "rua": forms.TextInput(attrs={"class": "form-control", "placeholder": "Logradouro"}),
            "numero": forms.TextInput(attrs={"class": "form-control", "placeholder": "Número"}),
            "bairro": forms.TextInput(attrs={"class": "form-control", "placeholder": "Bairro"}),
            "cidade": forms.TextInput(attrs={"class": "form-control", "placeholder": "Cidade"}),
        }
        labels = {"cnpj_cpf": "CNPJ/CPF", "rua": "Logradouro", "logomarca": "Logomarca"}

    def clean_cnpj_cpf(self):
        value = self.cleaned_data.get("cnpj_cpf", "")
        return _validate_cnpj_cpf(value)

class UsuarioBaseForm(forms.ModelForm):
    data_cadastro = forms.DateField(
        label="Data de cadastro",
        required=False,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "form-control",
                "placeholder": "dd/mm/aaaa",
                "inputmode": "numeric",
                "data-date-picker": "br",
                "autocomplete": "off",
            },
        ),
    )
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "email_recuperacao",
            "telefone_recuperacao",
            "first_name",
            "last_name",
            "is_manager",
            "is_active",
        ]

    def __init__(self, *args, user=None, **kwargs):
        self.request_user = user
        super().__init__(*args, **kwargs)
        empresa = self._get_empresa()
        joined_at = _coerce_display_date(getattr(self.instance, "date_joined", None))
        if not joined_at:
            joined_at = _coerce_display_date(timezone.now())
        self.initial.setdefault("data_cadastro", joined_at)
        if "data_cadastro" in self.fields:
            self.fields["data_cadastro"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
            self.fields["data_cadastro"].disabled = True
        if "is_manager" in self.fields and getattr(empresa, "plano", None) != "PLUS":
            self.fields.pop("is_manager", None)
        if "is_active" in self.fields:
            current = self.instance.is_active if self.instance.pk else True
            self.fields["is_active"] = forms.TypedChoiceField(
                label="Ativo",
                choices=(("True", "Sim"), ("False", "Não")),
                coerce=lambda value: value == "True",
                widget=forms.RadioSelect,
                initial=current,
            )
        if "is_manager" in self.fields:
            self.fields["is_manager"].label = "Gerente"
            self.fields["is_manager"].help_text = (
                "Se marcado, o usuário pode gerenciar equipe, relatórios e configurações da empresa."
            )
        if "is_active" in self.fields:
            self.fields["is_active"].help_text = "Se selecionar Não, o usuário não consegue acessar o sistema."
        if "username" in self.fields:
            self.fields["username"].label = "Login"
            self.fields["username"].widget.attrs.setdefault("placeholder", "Digite o login")
            self.fields["username"].widget.attrs.setdefault("autocomplete", "username")
            self.fields["username"].widget.attrs.setdefault("autofocus", "autofocus")
        if "email" in self.fields:
            self.fields["email"].label = "Endereço de e-mail"
            self.fields["email"].widget.attrs.setdefault("placeholder", "email@empresa.com")
            self.fields["email"].widget.attrs.setdefault("autocomplete", "email")
        if "email_recuperacao" in self.fields:
            self.fields["email_recuperacao"].label = "E-mail para recuperação de senha"
            self.fields["email_recuperacao"].widget.attrs.setdefault(
                "placeholder", "email@recuperacao.com"
            )
            self.fields["email_recuperacao"].widget.attrs.setdefault("autocomplete", "email")
        if "telefone_recuperacao" in self.fields:
            self.fields["telefone_recuperacao"].label = "Telefone para recuperação de senha"
            self.fields["telefone_recuperacao"].widget.attrs.setdefault(
                "placeholder", "(99)99999-9999"
            )
            self.fields["telefone_recuperacao"].widget.attrs.setdefault("data-mask", "phone")
        if "first_name" in self.fields:
            self.fields["first_name"].widget.attrs.setdefault("placeholder", "Nome")
            self.fields["first_name"].widget.attrs.setdefault("autocomplete", "given-name")
        if "last_name" in self.fields:
            self.fields["last_name"].widget.attrs.setdefault("placeholder", "Sobrenome")
            self.fields["last_name"].widget.attrs.setdefault("autocomplete", "family-name")
        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.setdefault("placeholder", "Crie uma senha")
            self.fields["password1"].widget.attrs.setdefault("autocomplete", "new-password")
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.setdefault("placeholder", "Confirme a senha")
            self.fields["password2"].widget.attrs.setdefault("autocomplete", "new-password")
        for name in (
            "username",
            "email",
            "email_recuperacao",
            "telefone_recuperacao",
            "first_name",
            "last_name",
            "password1",
            "password2",
        ):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-control")
        for name in ("is_manager", "is_active"):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-check-input")
        if "password1" in self.fields:
            help_texts = password_validators_help_texts()
            if help_texts:
                items = "".join(f"<li>{text}</li>" for text in help_texts)
                self.fields["password1"].help_text = mark_safe(f"<ul class=\"mb-0\">{items}</ul>")

    def _get_empresa(self):
        return getattr(self.request_user, "empresa", None)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1") or ""
        password2 = self.cleaned_data.get("password2") or ""
        if self._password_is_required() or password1 or password2:
            if not password1 or not password2:
                raise forms.ValidationError("Informe a senha duas vezes.")
            if password1 != password2:
                raise forms.ValidationError("As senhas não conferem.")
            validate_password(password1, self.instance)
        return password2

    def clean(self):
        cleaned = super().clean()
        empresa = self._get_empresa()
        if not empresa:
            raise forms.ValidationError("Empresa não encontrada.")

        is_active = bool(cleaned.get("is_active", False))
        is_manager = bool(cleaned.get("is_manager", False))

        if is_active and (not self.instance.pk or not self.instance.is_active):
            ativos = User.objects.filter(empresa=empresa, is_active=True).count()
            if ativos >= empresa.limite_funcionarios():
                raise forms.ValidationError(
                    "Limite de usuarios ativos atingido. Considere o plano PLUS para aumentar o limite."
                )

        if is_active and is_manager and (
            not self.instance.pk or not self.instance.is_manager or not self.instance.is_active
        ):
            gerentes = User.objects.filter(empresa=empresa, is_active=True, is_manager=True).count()
            if gerentes >= empresa.limite_gerentes():
                raise forms.ValidationError(
                    "Limite de gerentes atingido. Considere o plano PLUS para aumentar o limite."
                )

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        empresa = self._get_empresa()
        if empresa:
            user.empresa = empresa

        password = self.cleaned_data.get("password1") or ""
        if password:
            user.set_password(password)

        if commit:
            user.save()
            self._sync_groups(user)
        else:
            self._pending_group_sync = True
        return user

    def _sync_groups(self, user):
        manager_group, _ = Group.objects.get_or_create(name=ROLE_MANAGER)
        employee_group, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)
        if "is_manager" not in self.cleaned_data:
            if not user.is_manager:
                user.groups.add(employee_group)
            return
        if self.cleaned_data.get("is_manager"):
            user.groups.add(manager_group)
            user.groups.remove(employee_group)
        else:
            user.groups.add(employee_group)
            user.groups.remove(manager_group)

    def _password_is_required(self):
        return False


class AutoCadastroForm(forms.Form):
    empresa_nome = forms.CharField(label="Nome da empresa", max_length=150)
    cnpj_cpf = forms.CharField(label="CNPJ/CPF", max_length=20, required=False)
    telefone = forms.CharField(label="Telefone", max_length=20, required=False)
    cep = forms.CharField(label="CEP", max_length=12)
    rua = forms.CharField(label="Logradouro", max_length=150, required=False)
    numero = forms.CharField(label="Número", max_length=20, required=False)
    bairro = forms.CharField(label="Bairro", max_length=100, required=False)
    cidade = forms.CharField(label="Cidade", max_length=100, required=False)
    logomarca = forms.ImageField(
        label="Logomarca (opcional)",
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    username = forms.CharField(label="Login", max_length=150)
    email = forms.EmailField(label="E-mail")
    email_recuperacao = forms.EmailField(label="E-mail para recuperação de senha")
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa_nome"].widget.attrs.update(
            {"placeholder": "Nome da oficina", "autocomplete": "organization"}
        )
        self.fields["cnpj_cpf"].widget.attrs.update(
            {"placeholder": "CNPJ ou CPF", "autocomplete": "off", "data-mask": "cnpj-cpf", "inputmode": "numeric"}
        )
        self.fields["telefone"].widget.attrs.update(
            {"placeholder": "(99)99999-9999", "data-mask": "phone", "autocomplete": "tel"}
        )
        self.fields["cep"].widget.attrs.update(
            {
                "placeholder": "00000-000",
                "data-mask": "cep",
                "inputmode": "numeric",
                "data-lookup": "viacep",
                "autocomplete": "postal-code",
            }
        )
        self.fields["rua"].widget.attrs.update(
            {"placeholder": "Logradouro", "autocomplete": "street-address"}
        )
        self.fields["numero"].widget.attrs.update(
            {"placeholder": "Número", "autocomplete": "address-line2"}
        )
        self.fields["bairro"].widget.attrs.update(
            {"placeholder": "Bairro", "autocomplete": "address-level3"}
        )
        self.fields["cidade"].widget.attrs.update(
            {"placeholder": "Cidade", "autocomplete": "address-level2"}
        )
        self.fields["logomarca"].widget.attrs.update({"accept": "image/*"})
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Digite um login", "autocomplete": "username"}
        )
        self.fields["email"].widget.attrs.update(
            {"placeholder": "email@empresa.com", "autocomplete": "email"}
        )
        self.fields["email_recuperacao"].widget.attrs.update(
            {"placeholder": "email@recuperacao.com", "autocomplete": "email"}
        )
        self.fields["first_name"].widget.attrs.update(
            {"placeholder": "Seu nome", "autocomplete": "given-name"}
        )
        self.fields["last_name"].widget.attrs.update(
            {"placeholder": "Sobrenome", "autocomplete": "family-name"}
        )
        self.fields["password1"].widget.attrs.update(
            {"placeholder": "Crie uma senha", "autocomplete": "new-password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"placeholder": "Confirme a senha", "autocomplete": "new-password"}
        )
        for name in self.fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        help_texts = password_validators_help_texts()
        if help_texts:
            items = "".join(f"<li>{text}</li>" for text in help_texts)
            self.fields["password1"].help_text = mark_safe(f"<ul class=\"mb-0\">{items}</ul>")

    def clean_empresa_nome(self):
        nome = (self.cleaned_data.get("empresa_nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Informe o nome da empresa.")
        return nome

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Este login já está em uso.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        existing_user = User.objects.filter(email__iexact=email).select_related("empresa").first()
        if existing_user:
            empresa = getattr(existing_user, "empresa", None)
            if empresa and not empresa.pagamento_confirmado:
                raise forms.ValidationError(
                    "Já existe um cadastro pendente para este e-mail. "
                    "Aguarde a liberação ou entre em contato com o suporte."
                )
            raise forms.ValidationError(
                "Este e-mail já está em uso. Se você já possui conta, faça login ou recupere a senha."
            )
        return email

    def clean_email_recuperacao(self):
        email = (self.cleaned_data.get("email_recuperacao") or "").strip()
        if not email:
            raise forms.ValidationError("Informe um e-mail para recuperação de senha.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1") or ""
        password2 = self.cleaned_data.get("password2") or ""
        if not password1 or not password2:
            raise forms.ValidationError("Informe a senha duas vezes.")
        if password1 != password2:
            raise forms.ValidationError("As senhas não conferem.")
        validate_password(password1)
        return password2

    def clean_cnpj_cpf(self):
        value = self.cleaned_data.get("cnpj_cpf", "")
        return _validate_cnpj_cpf(value)

    def clean_cep(self):
        cep = (self.cleaned_data.get("cep") or "").strip().upper()
        digits = re.sub(r"\D", "", cep)
        if not digits:
            raise forms.ValidationError("Informe o CEP.")
        if len(digits) != 8:
            raise forms.ValidationError("CEP deve ter 8 dígitos.")
        return f"{digits[:5]}-{digits[5:]}"

    def save(self):
        data = self.cleaned_data
        with transaction.atomic():
            empresa = Empresa.objects.create(
                nome=data["empresa_nome"],
                cnpj_cpf=data.get("cnpj_cpf", ""),
                telefone=data.get("telefone", ""),
                cep=data.get("cep", ""),
                rua=data.get("rua", ""),
                numero=data.get("numero", ""),
                bairro=data.get("bairro", ""),
                cidade=data.get("cidade", ""),
                logomarca=data.get("logomarca"),
                senha_temporaria=data.get("password1", ""),
            )
            user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                email_recuperacao=data.get("email_recuperacao", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                password=data["password1"],
                empresa=empresa,
                is_manager=True,
            )
            manager_group, _ = Group.objects.get_or_create(name=ROLE_MANAGER)
            employee_group, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)
            user.groups.add(manager_group)
            user.groups.remove(employee_group)
        return user


class UsuarioCreateForm(UsuarioBaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = True
        self.fields["password2"].required = True

    def _password_is_required(self):
        return True


class UsuarioUpdateForm(UsuarioBaseForm):
    pass


class PasswordRecoveryForm(forms.Form):
    identificador = forms.CharField(
        label="E-mail ou telefone",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite seu e-mail ou telefone",
                "autocomplete": "email",
                "data-mask": "phone",
                "data-allow-email": "true",
            }
        ),
    )

    def clean_identificador(self):
        value = (self.cleaned_data.get("identificador") or "").strip()
        if not value:
            raise forms.ValidationError("Informe e-mail ou telefone para recuperar a senha.")
        return value
