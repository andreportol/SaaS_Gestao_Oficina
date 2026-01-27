from .models import Empresa


def renovacoes_pendentes(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_superuser:
        return {
            "renovacoes_pendentes": [],
            "renovacoes_pendentes_count": 0,
            "cadastros_pendentes_count": 0,
        }

    qs = Empresa.objects.filter(renovacao_periodo__isnull=False).exclude(renovacao_periodo="")
    qs = qs.order_by("-renovacao_solicitada_em", "-criado_em")
    cadastros_pendentes_count = Empresa.objects.filter(pagamento_confirmado=False).count()
    return {
        "renovacoes_pendentes": list(qs[:10]),
        "renovacoes_pendentes_count": qs.count(),
        "cadastros_pendentes_count": cadastros_pendentes_count,
    }
