from datetime import timedelta
from io import BytesIO
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.urls import reverse


class Empresa(models.Model):
    class Plano(models.TextChoices):
        BASICO = "BASICO", "Basico"
        PLUS = "PLUS", "Plus"

    class PlanoPeriodo(models.TextChoices):
        MENSAL = "30d", "30 dias"
        SEMESTRAL = "6m", "6 meses"
        ANUAL = "12m", "12 meses"

    nome = models.CharField(max_length=150)
    cnpj_cpf = models.CharField(max_length=20, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    logomarca = models.ImageField(
        upload_to="empresas/logos/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    cep = models.CharField(max_length=12, blank=True, default="")
    rua = models.CharField(max_length=150, blank=True, default="")
    numero = models.CharField(max_length=20, blank=True, default="")
    bairro = models.CharField(max_length=100, blank=True, default="")
    cidade = models.CharField(max_length=100, blank=True, default="")
    plano = models.CharField(max_length=10, choices=Plano.choices, default=Plano.BASICO)
    plano_periodo = models.CharField(max_length=3, choices=PlanoPeriodo.choices, default=PlanoPeriodo.MENSAL)
    plano_atualizado_em = models.DateTimeField(blank=True, null=True)
    plano_vencimento_em = models.DateTimeField(blank=True, null=True)
    is_ativo = models.BooleanField(default=True)
    pagamento_confirmado = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.nome

    def limite_funcionarios(self) -> int:
        if self.plano == self.Plano.PLUS:
            return 30
        return 6

    def limite_gerentes(self) -> int:
        if self.plano == self.Plano.PLUS:
            return 3
        return 1

    def save(self, *args, **kwargs):
        previous = None
        if self.pk:
            previous = Empresa.objects.filter(pk=self.pk).values(
                "plano",
                "plano_periodo",
                "plano_atualizado_em",
                "plano_vencimento_em",
                "logomarca",
            ).first()

        logo_changed = False
        if self.logomarca:
            if not previous:
                logo_changed = True
            else:
                logo_changed = previous.get("logomarca") != self.logomarca.name

        if self.logomarca and logo_changed and not getattr(self, "_logomarca_processed", False):
            self._process_logomarca()

        if self.plano_atualizado_em is None:
            self.plano_atualizado_em = timezone.now()

        plan_changed = False
        if previous:
            plan_changed = (
                previous["plano"] != self.plano
                or previous["plano_periodo"] != self.plano_periodo
            )

        if plan_changed:
            self.plano_atualizado_em = timezone.now()

        updated_changed = False
        if previous:
            updated_changed = previous["plano_atualizado_em"] != self.plano_atualizado_em

        should_recalc = (
            self.plano_vencimento_em is None
            or plan_changed
            or updated_changed
        )

        if should_recalc and self.plano_atualizado_em:
            days_map = {
                self.PlanoPeriodo.MENSAL: 30,
                self.PlanoPeriodo.SEMESTRAL: 182,
                self.PlanoPeriodo.ANUAL: 365,
            }
            self.plano_vencimento_em = self.plano_atualizado_em + timedelta(
                days=days_map.get(self.plano_periodo, 30)
            )

        if self.plano_vencimento_calculado():
            self.is_ativo = not self.plano_vencido()

        super().save(*args, **kwargs)

    def plano_atualizado_display(self):
        return self.plano_atualizado_em or self.criado_em

    def plano_vencimento_calculado(self):
        if self.plano_vencimento_em:
            return self.plano_vencimento_em
        base = self.plano_atualizado_em or self.criado_em
        if not base:
            return None
        days_map = {
            self.PlanoPeriodo.MENSAL: 30,
            self.PlanoPeriodo.SEMESTRAL: 182,
            self.PlanoPeriodo.ANUAL: 365,
        }
        return base + timedelta(days=days_map.get(self.plano_periodo, 30))

    def plano_vencido(self):
        vencimento = self.plano_vencimento_calculado()
        if not vencimento:
            return False
        if timezone.is_naive(vencimento):
            return vencimento.date() <= timezone.now().date()
        return vencimento.date() <= timezone.localdate()

    def dias_para_vencimento(self):
        vencimento = self.plano_vencimento_calculado()
        if not vencimento:
            return None
        return (vencimento.date() - timezone.now().date()).days

    def _process_logomarca(self):
        try:
            from PIL import Image
        except ImportError:
            return

        try:
            file_obj = self.logomarca.file
        except Exception:
            return

        try:
            file_obj.seek(0)
            image = Image.open(file_obj)
            image_format = (image.format or "").upper()
        except Exception:
            return

        max_size = (600, 600)
        image.thumbnail(max_size)
        if image_format not in {"JPEG", "JPG", "PNG", "WEBP"}:
            image_format = "PNG"

        buffer = BytesIO()
        save_kwargs = {}
        if image_format in {"JPEG", "JPG"}:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            save_kwargs.update({"format": "JPEG", "quality": 82, "optimize": True})
            ext = "jpg"
        elif image_format == "WEBP":
            save_kwargs.update({"format": "WEBP", "quality": 82, "method": 6})
            ext = "webp"
        else:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            save_kwargs.update({"format": "PNG", "optimize": True})
            ext = "png"

        try:
            image.save(buffer, **save_kwargs)
        except Exception:
            return

        buffer.seek(0)
        filename = f"logomarca.{ext}"
        self.logomarca.save(filename, ContentFile(buffer.read()), save=False)
        self._logomarca_processed = True


class UsuarioManager(UserManager):
    def _create_user(self, username, email, password, **extra_fields):
        empresa = extra_fields.get("empresa")
        if not extra_fields.get("is_superuser") and not empresa:
            raise ValueError("Usuários comuns precisam estar vinculados a uma empresa.")
        return super()._create_user(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="usuarios", null=True, blank=True)
    is_manager = models.BooleanField(default=False)
    REQUIRED_FIELDS = ["email"]

    objects = UsuarioManager()

    def __str__(self) -> str:
        empresa = self.empresa.nome if self.empresa else "Sem empresa"
        return f"{self.username} - {empresa}"

    def is_gerente(self) -> bool:
        if self.is_superuser or self.is_manager:
            return True
        return self.groups.filter(name="Gerente").exists()


class Funcionario(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="funcionarios")
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    data_ingresso = models.DateField(default=timezone.now)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    def logomarca_existe(self) -> bool:
        if not self.logomarca:
            return False
        storage = getattr(self.logomarca, "storage", None) or default_storage
        try:
            return storage.exists(self.logomarca.name)
        except Exception:
            return False

    def logomarca_url(self) -> str:
        if not self.logomarca_existe():
            return ""
        try:
            return self.logomarca.url
        except Exception:
            return ""


class Cliente(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="clientes")
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    documento = models.CharField(max_length=30, blank=True)
    cep = models.CharField(max_length=12, blank=True, default="")
    rua = models.CharField(max_length=150, blank=True, default="")
    numero = models.CharField(max_length=20, blank=True, default="")
    bairro = models.CharField(max_length=100, blank=True, default="")
    cidade = models.CharField(max_length=100, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    def save(self, *args, **kwargs):
        if self.nome:
            self.nome = self.nome.strip().upper()
        super().save(*args, **kwargs)


class Veiculo(models.Model):
    class Tipo(models.TextChoices):
        MOTO = "MOTO", "Moto"
        CARRO = "CARRO", "Carro"
        CAMINHAO = "CAMINHAO", "Caminhão"

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="veiculos")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="veiculos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    placa = models.CharField(max_length=10)
    marca = models.CharField(max_length=50)
    modelo = models.CharField(max_length=50)
    ano = models.CharField(max_length=9, blank=True, null=True)
    cor = models.CharField(max_length=30, blank=True)
    km = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["placa"]
        unique_together = ("empresa", "placa")

    def __str__(self) -> str:
        return f"{self.placa} - {self.modelo}"


class Agenda(models.Model):
    class Tipo(models.TextChoices):
        ENTREGA = "ENTREGA", "Entrega (deixar)"
        RETIRADA = "RETIRADA", "Retirada (buscar)"
        NOTA = "NOTA", "Anotação"

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="agendas")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="agendas")
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name="agendamentos")
    data_agendada = models.DateField()
    hora_agendada = models.TimeField(null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.NOTA)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_agendada", "-hora_agendada", "-id"]
        unique_together = ("empresa", "cliente", "veiculo", "data_agendada", "hora_agendada")

    def __str__(self) -> str:
        hora = f" {self.hora_agendada.strftime('%H:%M')}" if self.hora_agendada else ""
        return f"{self.data_agendada}{hora} - {self.cliente.nome}"

    def get_absolute_url(self):
        return reverse("agenda")


class Produto(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="produtos")
    nome = models.CharField(max_length=150)
    codigo = models.CharField(max_length=50, blank=True)
    descricao = models.TextField(blank=True)
    custo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    estoque_atual = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    estoque_minimo = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["nome"]
        unique_together = ("empresa", "nome")

    def __str__(self) -> str:
        return self.nome


class OrdemServico(models.Model):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        EXECUCAO = "EXECUCAO", "Em Execução"
        AGUARDANDO_PECA = "AGUARDANDO_PECA", "Aguardando Peça"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="ordens_servico")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="ordens_servico")
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name="ordens_servico")
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="os_responsavel",
        null=True,
        blank=True,
    )
    executor = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        related_name="os_execucoes",
        null=True,
        blank=True,
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="os_criadas",
        null=True,
        blank=True,
    )
    finalizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="os_finalizadas",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTA)
    entrada_em = models.DateField(default=timezone.now)
    previsao_entrega = models.DateField(blank=True, null=True)
    iniciado_em = models.DateTimeField(blank=True, null=True)
    finalizado_em = models.DateTimeField(blank=True, null=True)
    problema = models.TextField()
    diagnostico = models.TextField(blank=True)
    mao_de_obra = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    observacoes = models.TextField(blank=True)
    anexo = models.FileField(
        upload_to="anexos/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "pdf"])],
    )
    total_cache = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entrada_em", "-id"]

    def __str__(self) -> str:
        return f"OS #{self.id} - {self.cliente.nome}"

    @property
    def total_itens(self) -> Decimal:
        return self.itens.aggregate(total=models.Sum("subtotal"))["total"] or Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return self.total_itens + self.mao_de_obra - self.desconto

    @property
    def total_pago(self) -> Decimal:
        return self.pagamentos.aggregate(total=models.Sum("valor"))["total"] or Decimal("0.00")

    @property
    def saldo(self) -> Decimal:
        return self.total - self.total_pago


class OrdemServicoLog(models.Model):
    class Acao(models.TextChoices):
        CRIAR = "CRIAR", "Criar"
        ATRIBUIR = "ATRIBUIR", "Atribuir"
        INICIAR = "INICIAR", "Iniciar"
        FINALIZAR = "FINALIZAR", "Finalizar"
        CANCELAR = "CANCELAR", "Cancelar"
        EDITAR = "EDITAR", "Editar"

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="os_logs")
    os = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="logs")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    acao = models.CharField(max_length=30, choices=Acao.choices)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]


class OSItem(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="os_itens")
    os = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, related_name="itens", null=True, blank=True)
    descricao = models.CharField(max_length=255)
    qtd = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.subtotal = (self.qtd or Decimal("0")) * (self.valor_unitario or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.descricao


class Pagamento(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pagamentos")
    os = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="pagamentos")
    class Metodo(models.TextChoices):
        DEBITO = "Cartão de Débito", "Cartão de Débito"
        CREDITO = "Cartão de Crédito", "Cartão de Crédito"
        DINHEIRO = "Dinheiro", "Dinheiro"
        PIX = "PIX", "PIX"
        CHEQUE = "Cheque", "Cheque"
        OUTRO = "Outro", "Outro"

    forma_pagamento = models.CharField(max_length=30, choices=Metodo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    pago_em = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-pago_em", "-id"]

    def __str__(self) -> str:
        return f"Pagamento {self.valor} em {self.pago_em}"


class Despesa(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="despesas")
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    data = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return self.descricao
