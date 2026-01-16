from django.db.models import Q

from .models import OrdemServico, OrdemServicoLog


def is_manager_user(user) -> bool:
    checker = getattr(user, "is_gerente", None)
    if callable(checker):
        return checker()
    return bool(checker)


def os_queryset_for_user(user, qs=None):
    qs = qs or OrdemServico.objects.all()
    empresa = getattr(user, "empresa", None)
    if empresa:
        qs = qs.filter(empresa=empresa)
    else:
        return qs.none()
    if not is_manager_user(user):
        qs = qs.filter(Q(responsavel=user))
    return qs


def criar_os_log(os, usuario, acao, observacao=""):
    return OrdemServicoLog.objects.create(
        empresa=os.empresa,
        os=os,
        usuario=usuario,
        acao=acao,
        observacao=observacao,
    )
