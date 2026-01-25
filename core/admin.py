from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Cliente,
    Despesa,
    Empresa,
    Funcionario,
    OrdemServico,
    OrdemServicoLog,
    OSItem,
    Pagamento,
    Produto,
    Usuario,
    Veiculo,
)


class EmpresaAdminMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        empresa = getattr(request.user, "empresa", None)
        if hasattr(qs.model, "empresa") and empresa:
            return qs.filter(empresa=empresa)
        return qs.none()

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "empresa") and not obj.empresa_id and not request.user.is_superuser:
            obj.empresa = request.user.empresa
        return super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        perm = f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}"
        return request.user.has_perm(perm)


@admin.register(Usuario)
class UsuarioAdmin(EmpresaAdminMixin, UserAdmin):
    fieldsets = (
        ("Credenciais", {"fields": ("username", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Empresa", {"fields": ("empresa", "is_manager")}),
        ("Permissoes", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "empresa", "is_manager", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "empresa", "is_manager", "is_staff")
    list_filter = ("empresa", "is_manager", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")


@admin.register(Funcionario)
class FuncionarioAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Dados do funcionario", {"fields": ("empresa", "nome", "telefone", "email", "data_ingresso", "ativo")}),
        ("Controle", {"fields": ("criado_em",)}),
    )
    list_display = ("nome", "telefone", "email", "data_ingresso", "ativo", "empresa")
    list_filter = ("ativo", "empresa")
    search_fields = ("nome", "telefone", "email")
    readonly_fields = ("criado_em",)


@admin.register(Empresa)
class EmpresaAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        (
            "Dados da empresa",
            {"fields": ("nome", "cnpj_cpf", "telefone", "cep", "rua", "numero", "bairro", "cidade", "logomarca")},
        ),
        (
            "Plano",
            {
                "fields": (
                    "plano",
                    "plano_periodo",
                    "plano_atualizado_em",
                    "plano_vencimento_em",
                    "is_ativo",
                    "pagamento_confirmado",
                )
            },
        ),
        ("Controle", {"fields": ("criado_em",)}),
    )
    list_display = (
        "nome",
        "cnpj_cpf",
        "telefone",
        "plano",
        "plano_periodo",
        "is_ativo",
        "pagamento_confirmado",
        "criado_em",
    )
    search_fields = ("nome", "cnpj_cpf", "telefone")
    list_filter = ("plano", "plano_periodo", "is_ativo", "pagamento_confirmado")
    readonly_fields = ("criado_em",)


@admin.register(Cliente)
class ClienteAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Identificacao", {"fields": ("empresa", "nome", "documento")}),
        ("Contato", {"fields": ("telefone", "email")}),
        ("Endereco", {"fields": ("cep", "rua", "numero", "bairro", "cidade")}),
        ("Controle", {"fields": ("criado_em",)}),
    )
    list_display = ("nome", "telefone", "empresa")
    search_fields = ("nome", "telefone", "email")
    list_filter = ("empresa",)
    readonly_fields = ("criado_em",)


@admin.register(Veiculo)
class VeiculoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Relacionamentos", {"fields": ("empresa", "cliente")}),
        ("Veiculo", {"fields": ("tipo", "placa", "marca", "modelo", "ano", "cor", "km")}),
    )
    list_display = ("placa", "modelo", "km", "cliente", "empresa")
    search_fields = ("placa", "modelo", "marca")
    list_filter = ("tipo", "empresa")


@admin.register(Produto)
class ProdutoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Identificacao", {"fields": ("empresa", "nome", "codigo")}),
        ("Descricao", {"fields": ("descricao",)}),
        ("Valores e estoque", {"fields": ("custo", "preco", "estoque_atual", "estoque_minimo")}),
    )
    list_display = ("nome", "codigo", "preco", "estoque_atual", "estoque_minimo", "empresa")
    search_fields = ("nome", "codigo")
    list_filter = ("empresa",)


@admin.register(OrdemServico)
class OrdemServicoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Identificacao", {"fields": ("empresa", "status")}),
        ("Cliente e veiculo", {"fields": ("cliente", "veiculo", "responsavel", "executor")}),
        ("Datas", {"fields": ("entrada_em", "previsao_entrega")}),
        ("Descricao", {"fields": ("problema", "diagnostico", "observacoes")}),
        ("Valores", {"fields": ("mao_de_obra", "desconto", "total_cache")}),
        ("Anexo", {"fields": ("anexo",)}),
        ("Controle", {"fields": ("criado_em", "criado_por", "iniciado_em", "finalizado_em", "finalizado_por")}),
    )
    list_display = ("id", "cliente", "veiculo", "status", "entrada_em", "empresa")
    list_filter = ("status", "empresa")
    search_fields = ("cliente__nome", "veiculo__placa")
    readonly_fields = ("criado_em", "iniciado_em", "finalizado_em")


@admin.register(OSItem)
class OSItemAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Vinculos", {"fields": ("empresa", "os", "produto")}),
        ("Detalhes", {"fields": ("descricao", "qtd", "valor_unitario", "subtotal")}),
    )
    list_display = ("descricao", "os", "produto", "qtd", "valor_unitario", "subtotal", "empresa")
    search_fields = ("descricao", "produto__nome", "os__id")
    list_filter = ("empresa",)
    readonly_fields = ("subtotal",)


@admin.register(Pagamento)
class PagamentoAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Pagamento", {"fields": ("empresa", "os")}),
        ("Dados", {"fields": ("forma_pagamento", "valor", "pago_em")}),
    )
    list_display = ("os", "forma_pagamento", "valor", "pago_em", "empresa")
    list_filter = ("forma_pagamento", "empresa")
    search_fields = ("os__id",)


@admin.register(Despesa)
class DespesaAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Despesa", {"fields": ("empresa", "descricao")}),
        ("Valores", {"fields": ("valor", "data")}),
    )
    list_display = ("descricao", "valor", "data", "empresa")
    list_filter = ("empresa", "data")
    search_fields = ("descricao",)


@admin.register(OrdemServicoLog)
class OrdemServicoLogAdmin(EmpresaAdminMixin, admin.ModelAdmin):
    list_display = ("os", "acao", "usuario", "criado_em", "empresa")
    list_filter = ("acao", "empresa")
    search_fields = ("os__id", "usuario__username")
    readonly_fields = ("empresa", "os", "usuario", "acao", "observacao", "criado_em")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
