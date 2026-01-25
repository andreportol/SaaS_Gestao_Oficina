from functools import wraps

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied


ROLE_MANAGER = "Gerente"
ROLE_EMPLOYEE = "Funcionario"
ROLE_MODELS = [
    "core.Cliente",
    "core.Veiculo",
    "core.Agenda",
    "core.Produto",
    "core.OrdemServico",
    "core.OSItem",
    "core.Pagamento",
    "core.Despesa",
]


def setup_roles() -> dict:
    manager_group, _ = Group.objects.get_or_create(name=ROLE_MANAGER)
    employee_group, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)

    manager_permissions = []
    employee_permissions = []

    for model_path in ROLE_MODELS:
        model = apps.get_model(model_path)
        content_type = ContentType.objects.get_for_model(model)
        model_name = model._meta.model_name
        manager_codenames = [
            f"view_{model_name}",
            f"add_{model_name}",
            f"change_{model_name}",
            f"delete_{model_name}",
        ]
        employee_codenames = [
            f"view_{model_name}",
            f"add_{model_name}",
            f"change_{model_name}",
        ]
        manager_permissions += list(
            Permission.objects.filter(content_type=content_type, codename__in=manager_codenames)
        )
        employee_permissions += list(
            Permission.objects.filter(content_type=content_type, codename__in=employee_codenames)
        )

    manager_group.permissions.add(*manager_permissions)
    employee_group.permissions.add(*employee_permissions)

    return {
        "manager_group": manager_group.name,
        "employee_group": employee_group.name,
        "manager_permissions": len(manager_permissions),
        "employee_permissions": len(employee_permissions),
    }


def manager_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            raise PermissionDenied
        is_manager = getattr(user, "is_gerente", None)
        if callable(is_manager):
            allowed = is_manager()
        else:
            allowed = bool(is_manager)
        if not allowed:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped
