import json
import re
from decimal import Decimal

from django import forms
from django.db import models
from django.utils import timezone

from .models import Agenda, Cliente, Despesa, FormaPagamento, OrdemServico, OSItem, Pagamento, Produto, Veiculo


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


class VeiculoForm(EmpresaFormMixin):
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
            "Mottu (muito usada por entregadores)",
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
        fields = ["cliente", "tipo", "marca", "modelo", "ano", "cor", "placa"]
        widgets = {
            "placa": forms.TextInput(attrs={"placeholder": "ABC1D23", "style": "text-transform: uppercase;"}),
            "ano": forms.TextInput(
                attrs={"placeholder": "2023/2024", "data-mask": "ano-modelo", "inputmode": "numeric"}
            ),
            "modelo": forms.TextInput(attrs={"placeholder": "Onix Plus"}),
        }
        labels = {"ano": "Ano/Modelo"}

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
    class Meta:
        model = Produto
        fields = ["nome", "descricao", "codigo", "custo", "preco", "estoque_atual"]
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
        }


class AgendaForm(EmpresaFormMixin):
    class Meta:
        model = Agenda
        fields = ["cliente", "veiculo", "data_agendada", "hora_agendada", "tipo", "observacoes"]
        labels = {"data_agendada": "Data", "hora_agendada": "Hora", "tipo": "Tipo"}
        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "veiculo": forms.Select(attrs={"class": "form-select", "data-client-filter": "1"}),
            "data_agendada": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
            "hora_agendada": forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

    def clean(self):
        cleaned = super().clean()
        cliente = cleaned.get("cliente")
        veiculo = cleaned.get("veiculo")
        if cliente and veiculo and veiculo.cliente_id != cliente.id:
            self.add_error("veiculo", "Selecione um veículo do cliente escolhido.")
        return cleaned


class FormaPagamentoForm(EmpresaFormMixin):
    class Meta:
        model = FormaPagamento
        fields = ["nome", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"autofocus": "autofocus"}),
            "ativo": forms.CheckboxInput(attrs={"class": "big-check"}),
        }


class OrdemServicoForm(EmpresaFormMixin):
    class Meta:
        model = OrdemServico
        fields = [
            "cliente",
            "veiculo",
            "status",
            "entrada_em",
            "previsao_entrega",
            "problema",
            "diagnostico",
            "mao_de_obra",
            "desconto",
            "observacoes",
            "anexo",
        ]
        widgets = {
            "entrada_em": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "previsao_entrega": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "veiculo": forms.Select(attrs={"data-placeholder": "Selecione o veículo do cliente"}),
            "mao_de_obra": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
            "desconto": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "data-format": "currency2", "placeholder": "0,00"}
            ),
        }
        labels = {
            "mao_de_obra": "Mão de obra",
            "observacoes": "Observações",
            "desconto": "Desconto em Reais (R$)",
            "previsao_entrega": "Previsão de entrega",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self, "user", None)
        empresa = getattr(user, "empresa", None)

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

        date_format = "%Y-%m-%d"
        for name in ("entrada_em", "previsao_entrega"):
            if name in self.fields:
                self.fields[name].input_formats = [date_format]

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
            "pago_em": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control form-control-sm"}),
            "forma_pagamento": forms.Select(attrs={"class": "form-control form-control-sm"}),
            "valor": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("pago_em"):
            self.initial["pago_em"] = timezone.now().date()


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
