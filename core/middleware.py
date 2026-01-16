from typing import Optional

from django.http import HttpRequest


class EmpresaMiddleware:
    """Anexa a empresa do usuário autenticado à requisição."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.empresa: Optional[object] = None
        if getattr(request, "user", None) and request.user.is_authenticated:
            request.empresa = request.user.empresa
        response = self.get_response(request)
        return response
