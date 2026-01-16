from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Cliente, Despesa, Empresa, FormaPagamento, OrdemServico, OSItem, Pagamento, Produto, Usuario, Veiculo


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
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


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Dados da empresa", {"fields": ("nome", "cnpj_cpf", "telefone")}),
        ("Controle", {"fields": ("criado_em",)}),
    )
    list_display = ("nome", "cnpj_cpf", "telefone", "criado_em")
    search_fields = ("nome", "cnpj_cpf", "telefone")
    readonly_fields = ("criado_em",)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
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
class VeiculoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Relacionamentos", {"fields": ("empresa", "cliente")}),
        ("Veiculo", {"fields": ("tipo", "placa", "marca", "modelo", "ano", "cor")}),
    )
    list_display = ("placa", "modelo", "cliente", "empresa")
    search_fields = ("placa", "modelo", "marca")
    list_filter = ("tipo", "empresa")


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Identificacao", {"fields": ("empresa", "nome", "codigo")}),
        ("Descricao", {"fields": ("descricao",)}),
        ("Valores e estoque", {"fields": ("custo", "preco", "estoque_atual")}),
    )
    list_display = ("nome", "codigo", "preco", "estoque_atual", "empresa")
    search_fields = ("nome", "codigo")
    list_filter = ("empresa",)


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Forma de pagamento", {"fields": ("empresa", "nome", "ativo")}),
    )
    list_display = ("nome", "ativo", "empresa")
    list_filter = ("ativo", "empresa")
    search_fields = ("nome",)


@admin.register(OrdemServico)
class OrdemServicoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Identificacao", {"fields": ("empresa", "status")}),
        ("Cliente e veiculo", {"fields": ("cliente", "veiculo")}),
        ("Datas", {"fields": ("entrada_em", "previsao_entrega")}),
        ("Descricao", {"fields": ("problema", "diagnostico", "observacoes")}),
        ("Valores", {"fields": ("mao_de_obra", "desconto", "total_cache")}),
        ("Anexo", {"fields": ("anexo",)}),
        ("Controle", {"fields": ("criado_em",)}),
    )
    list_display = ("id", "cliente", "veiculo", "status", "entrada_em", "empresa")
    list_filter = ("status", "empresa")
    search_fields = ("cliente__nome", "veiculo__placa")
    readonly_fields = ("criado_em",)


@admin.register(OSItem)
class OSItemAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Vinculos", {"fields": ("empresa", "os", "produto")}),
        ("Detalhes", {"fields": ("descricao", "qtd", "valor_unitario", "subtotal")}),
    )
    list_display = ("descricao", "os", "produto", "qtd", "valor_unitario", "subtotal", "empresa")
    search_fields = ("descricao", "produto__nome", "os__id")
    list_filter = ("empresa",)
    readonly_fields = ("subtotal",)


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Pagamento", {"fields": ("empresa", "os")}),
        ("Dados", {"fields": ("forma_pagamento", "valor", "pago_em")}),
    )
    list_display = ("os", "forma_pagamento", "valor", "pago_em", "empresa")
    list_filter = ("forma_pagamento", "empresa")
    search_fields = ("os__id",)


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Despesa", {"fields": ("empresa", "descricao")}),
        ("Valores", {"fields": ("valor", "data")}),
    )
    list_display = ("descricao", "valor", "data", "empresa")
    list_filter = ("empresa", "data")
    search_fields = ("descricao",)
