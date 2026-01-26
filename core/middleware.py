from typing import Optional

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpRequest
from django.shortcuts import redirect


class EmpresaMiddleware:
    """Anexa a empresa do usuário autenticado à requisição."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.empresa: Optional[object] = None
        if (
            getattr(request, "user", None)
            and request.user.is_authenticated
            and request.path.startswith("/admin/login/")
            and request.method == "GET"
        ):
            logout(request)
        if getattr(request, "user", None) and request.user.is_authenticated:
            empresa_id = getattr(request.user, "empresa_id", None)
            if empresa_id:
                request.empresa = request.user.empresa.__class__.objects.filter(pk=empresa_id).first()
            else:
                request.empresa = None

            if request.empresa:
                vencido = request.empresa.plano_vencido()
                desired_status = (not vencido) and request.empresa.pagamento_confirmado
                if request.empresa.is_ativo != desired_status:
                    request.empresa.is_ativo = desired_status
                    request.empresa.save(update_fields=["is_ativo"])

            if (
                request.empresa
                and not request.empresa.pagamento_confirmado
                and not request.user.is_superuser
            ):
                logout(request)
                messages.error(
                    request,
                    "Cadastro recebido. Assim que o pagamento for confirmado, liberaremos o acesso ao sistema "
                    "e enviaremos uma notificação por e-mail ou WhatsApp.",
                )
                return redirect("login")

            if (
                request.empresa
                and not request.empresa.is_ativo
                and not request.user.is_superuser
            ):
                if request.path.startswith("/accounts/login/") and request.method == "POST":
                    return self.get_response(request)
                logout(request)
                messages.error(
                    request,
                    "Sua empresa está inativa. Entre em contato para regularizar.",
                )
                return redirect("login")
        response = self.get_response(request)
        return response
