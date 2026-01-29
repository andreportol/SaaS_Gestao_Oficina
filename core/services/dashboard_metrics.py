import calendar
from datetime import timedelta

from django.db.models import Avg, Count, F, Q, Sum, OuterRef, Subquery
from django.db.models.expressions import ExpressionWrapper
from django.db.models.fields import DateTimeField, DurationField
from django.db.models.functions import Cast, Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from ..models import Despesa, OrdemServico, OrdemServicoLog, OSItem, Pagamento, Produto
from . import is_manager_user, os_queryset_for_user


MESES_PT = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]


def _format_month(value):
    if not value:
        return ""
    return f"{MESES_PT[value.month - 1]}/{value.year}"


def _subtract_months(value, months):
    year = value.year - (months // 12)
    month = value.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _resolve_period(range_key=None, start=None, end=None, default_months=6, default_days=None):
    today = timezone.now().date()
    if start and end:
        if start > end:
            start, end = end, start
        return start, end
    if range_key:
        key = str(range_key).lower()
        if key.endswith("d") and key[:-1].isdigit():
            days = int(key[:-1])
            return today - timedelta(days=days - 1), today
        if key.endswith("m") and key[:-1].isdigit():
            months = int(key[:-1])
            start = _subtract_months(today.replace(day=1), max(months - 1, 0))
            return start, today
        if key.endswith("y") and key[:-1].isdigit():
            months = int(key[:-1]) * 12
            start = _subtract_months(today.replace(day=1), max(months - 1, 0))
            return start, today
    if default_days:
        return today - timedelta(days=default_days - 1), today
    start = _subtract_months(today.replace(day=1), max(default_months - 1, 0))
    return start, today


def _coerce_limit(value, fallback=10):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _merge_monthly(entradas, saidas):
    data = {}
    for row in entradas:
        data[row["period"]] = {
            "period": row["period"],
            "entradas": row["total"] or 0,
            "despesas": 0,
        }
    for row in saidas:
        if row["period"] in data:
            data[row["period"]]["despesas"] = row["total"] or 0
        else:
            data[row["period"]] = {
                "period": row["period"],
                "entradas": 0,
                "despesas": row["total"] or 0,
            }
    items = sorted(data.values(), key=lambda item: item["period"])
    for item in items:
        item["lucro"] = (item["entradas"] or 0) - (item["despesas"] or 0)
    return items


def build_dashboard_data(
    user,
    range_key=None,
    start=None,
    end=None,
    clientes_limit=10,
    recorrencia_limit=10,
    produtos_limit=10,
):
    empresa = getattr(user, "empresa", None)
    if not empresa:
        return {}

    clientes_limit = _coerce_limit(clientes_limit, 10)
    recorrencia_limit = _coerce_limit(recorrencia_limit, 10)
    produtos_limit = _coerce_limit(produtos_limit, 10)
    period_start, period_end = _resolve_period(range_key, start, end, default_months=6)
    op_start, op_end = period_start, period_end

    os_qs = os_queryset_for_user(user)
    pagamentos_qs = Pagamento.objects.filter(empresa=empresa)
    despesas_qs = Despesa.objects.filter(empresa=empresa)
    itens_qs = OSItem.objects.filter(empresa=empresa)
    produtos_qs = Produto.objects.filter(empresa=empresa)

    if not is_manager_user(user):
        pagamentos_qs = pagamentos_qs.filter(Q(os__responsavel=user) | Q(os__criado_por=user))
        itens_qs = itens_qs.filter(os__in=os_qs)

    pagamentos_periodo = pagamentos_qs.filter(pago_em__gte=period_start, pago_em__lte=period_end)
    despesas_periodo = despesas_qs.filter(data__gte=period_start, data__lte=period_end)

    entradas = (
        pagamentos_periodo.annotate(period=TruncMonth("pago_em"))
        .values("period")
        .annotate(total=Sum("valor"))
        .order_by("period")
    )
    saidas = (
        despesas_periodo.annotate(period=TruncMonth("data"))
        .values("period")
        .annotate(total=Sum("valor"))
        .order_by("period")
    )
    lucro_mensal = _merge_monthly(entradas, saidas)

    saldo_periodo = (pagamentos_periodo.aggregate(total=Sum("valor"))["total"] or 0) - (
        despesas_periodo.aggregate(total=Sum("valor"))["total"] or 0
    )
    saldo_geral = (pagamentos_qs.aggregate(total=Sum("valor"))["total"] or 0) - (
        despesas_qs.aggregate(total=Sum("valor"))["total"] or 0
    )

    os_periodo = os_qs.filter(entrada_em__gte=period_start, entrada_em__lte=period_end)
    os_por_funcionario = (
        os_periodo.annotate(executor_nome=Coalesce("executor__nome", "responsavel__username"))
        .values("executor_nome")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    os_por_funcionario_itens = (
        os_periodo.annotate(executor_nome=Coalesce("executor__nome", "responsavel__username"))
        .values("id", "executor_nome")
        .order_by("-id")
    )
    os_por_funcionario_map = {}
    for row in os_por_funcionario_itens:
        executor_nome = row["executor_nome"] or "Sem executor"
        os_por_funcionario_map.setdefault(executor_nome, []).append(row["id"])
    status_map = dict(OrdemServico.Status.choices)
    os_status = (
        os_periodo.values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )

    finalizado_log = (
        OrdemServicoLog.objects.filter(os_id=OuterRef("pk"), acao=OrdemServicoLog.Acao.FINALIZAR)
        .order_by("-criado_em")
        .values("criado_em")[:1]
    )
    os_finalizadas = (
        os_qs.filter(status=OrdemServico.Status.FINALIZADA)
        .annotate(
            finalizado_em_eff=Coalesce(
                "finalizado_em",
                Subquery(finalizado_log),
                F("criado_em"),
            )
        )
        .filter(
            finalizado_em_eff__isnull=False,
            finalizado_em_eff__date__gte=op_start,
            finalizado_em_eff__date__lte=op_end,
        )
    )
    duracao = ExpressionWrapper(
        F("finalizado_em_eff") - Cast("entrada_em", DateTimeField()), output_field=DurationField()
    )
    tempo_medio = (
        os_finalizadas.annotate(period=TruncDate("finalizado_em_eff"))
        .values("period")
        .annotate(media=Avg(duracao))
        .order_by("period")
    )

    itens_periodo = itens_qs.filter(os__entrada_em__gte=period_start, os__entrada_em__lte=period_end)
    produtos_top = (
        itens_periodo.values("produto__nome", "descricao")
        .annotate(qtd=Sum("qtd"), total=Sum("subtotal"))
        .order_by("-total")[:produtos_limit]
    )

    estoque_critico = produtos_qs.filter(
        estoque_atual__isnull=False,
        estoque_minimo__isnull=False,
        estoque_atual__lte=F("estoque_minimo"),
    ).order_by("estoque_atual", "nome")

    clientes_top = (
        pagamentos_periodo.values("os__cliente__nome")
        .annotate(total=Sum("valor"))
        .order_by("-total")[:clientes_limit]
    )

    recorrencia_top = (
        os_periodo.values("cliente__nome")
        .annotate(total_os=Count("id"))
        .order_by("-total_os")[:recorrencia_limit]
    )

    return {
        "periodo": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "operacional_start": op_start.isoformat(),
            "operacional_end": op_end.isoformat(),
        },
        "financeiro": {
            "lucro_mensal": {
                "labels": [_format_month(item["period"]) for item in lucro_mensal],
                "entradas": [float(item["entradas"] or 0) for item in lucro_mensal],
                "despesas": [float(item["despesas"] or 0) for item in lucro_mensal],
                "lucro": [float(item["lucro"] or 0) for item in lucro_mensal],
            },
            "saldo_periodo": float(saldo_periodo or 0),
            "saldo_geral": float(saldo_geral or 0),
        },
        "operacional": {
            "os_por_funcionario": {
                "labels": [row["executor_nome"] or "Sem executor" for row in os_por_funcionario],
                "valores": [row["total"] for row in os_por_funcionario],
            },
            "os_por_funcionario_detalhes": [
                {
                    "executor": row["executor_nome"] or "Sem executor",
                    "os": os_por_funcionario_map.get(row["executor_nome"] or "Sem executor", []),
                }
                for row in os_por_funcionario
            ],
            "status_os": {
                "labels": [status_map.get(row["status"], row["status"]) for row in os_status],
                "valores": [row["total"] for row in os_status],
            },
            "tempo_medio": {
                "labels": [row["period"].strftime("%d/%m") for row in tempo_medio],
                "dias": [
                    float((row["media"].total_seconds() / 86400) if row["media"] else 0)
                    for row in tempo_medio
                ],
            },
        },
        "produtos": {
            "mais_vendidos": {
                "labels": [
                    (row["produto__nome"] or row["descricao"] or "Produto")
                    for row in produtos_top
                ],
                "qtd": [float(row["qtd"] or 0) for row in produtos_top],
                "total": [float(row["total"] or 0) for row in produtos_top],
            },
            "estoque_critico": {
                "total": estoque_critico.count(),
                "itens": [
                    {
                        "nome": produto.nome,
                        "estoque_atual": produto.estoque_atual,
                        "estoque_minimo": produto.estoque_minimo,
                    }
                    for produto in estoque_critico[:10]
                ],
            },
        },
        "clientes": {
            "mais_lucrativos": {
                "labels": [row["os__cliente__nome"] for row in clientes_top],
                "valores": [float(row["total"] or 0) for row in clientes_top],
            },
            "recorrencia": {
                "labels": [row["cliente__nome"] or "Sem cliente" for row in recorrencia_top],
                "vezes": [row["total_os"] for row in recorrencia_top],
            },
        },
    }
