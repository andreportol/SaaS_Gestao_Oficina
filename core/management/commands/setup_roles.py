from django.core.management.base import BaseCommand

from core.permissions import setup_roles


class Command(BaseCommand):
    help = "Cria/atualiza grupos e permissoes padrao (Gerente/Funcionario)."

    def handle(self, *args, **options):
        summary = setup_roles()
        self.stdout.write(self.style.SUCCESS("Grupos e permissoes configurados."))
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary['manager_group']}: {summary['manager_permissions']} permissoes"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary['employee_group']}: {summary['employee_permissions']} permissoes"
            )
        )
