from datetime import datetime, timedelta
import re
import urllib.parse
import base64
from io import BytesIO
import mimetypes
from pathlib import Path
import csv
import json
import urllib.error
import urllib.request

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.dateparse import parse_date
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView
from django.views.generic.edit import FormMixin
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from .forms import (
    LoginForm,
    _notify_aprovacao_acesso,
    _notify_nova_liberacao,
    AutoCadastroForm,
    ClienteForm,
    DespesaForm,
    EmpresaUpdateForm,
    FuncionarioForm,
    OrdemServicoForm,
    OSItemForm,
    PagamentoForm,
    UsuarioCreateForm,
    UsuarioUpdateForm,
    AgendaForm,
    ProdutoForm,
    VeiculoForm,
    PasswordRecoveryForm,
)
from .models import (
    Agenda,
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
from .services import criar_os_log, os_queryset_for_user
from .services.dashboard_metrics import build_dashboard_data


class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        checker = getattr(self.request.user, "is_gerente", None)
        if callable(checker):
            return checker()
        return bool(checker)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return bool(self.request.user.is_superuser)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied


class EmpresaQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        qs = super().get_queryset()
        empresa = getattr(self.request.user, "empresa", None)
        if hasattr(qs.model, "empresa"):
            if empresa:
                qs = qs.filter(empresa=empresa)
            else:
                qs = qs.none()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        querydict = self.request.GET.copy()
        querydict.pop("page", None)
        context["querystring"] = querydict.urlencode()
        return context


class EmpresaFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if hasattr(form.instance, "empresa_id"):
            empresa = getattr(self.request.user, "empresa", None)
            if not empresa:
                form.add_error(None, "Empresa não encontrada. Vincule um usuário a uma empresa para cadastrar.")
                return self.form_invalid(form)
            form.instance.empresa = empresa
        return super().form_valid(form)


def _apply_os_status_audit(os, previous_status, usuario):
    actions = []
    now = timezone.now()
    if os.status == OrdemServico.Status.EXECUCAO and previous_status != os.status and not os.iniciado_em:
        os.iniciado_em = now
        actions.append(OrdemServicoLog.Acao.INICIAR)
    if os.status == OrdemServico.Status.FINALIZADA and previous_status != os.status:
        if not os.finalizado_em:
            os.finalizado_em = now
        os.finalizado_por = usuario
        actions.append(OrdemServicoLog.Acao.FINALIZAR)
    if os.status == OrdemServico.Status.CANCELADA and previous_status != os.status:
        actions.append(OrdemServicoLog.Acao.CANCELAR)
    return actions


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_gerente():
            return redirect("clientes_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        hoje = timezone.now().date()
        inicio_periodo = hoje - timedelta(days=30)
        ordens = os_queryset_for_user(self.request.user)
        dashboard_data = build_dashboard_data(self.request.user, range_key=self.request.GET.get("range"))
        context.update(
            {
                "os_abertas": ordens.filter(status=OrdemServico.Status.ABERTA).count(),
                "os_aguardando": ordens.filter(status=OrdemServico.Status.AGUARDANDO_PECA).count(),
                "os_execucao": ordens.filter(status=OrdemServico.Status.EXECUCAO).count(),
                "os_finalizadas_periodo": ordens.filter(
                    status=OrdemServico.Status.FINALIZADA, entrada_em__gte=inicio_periodo
                ).count(),
                "pagamentos_periodo": Pagamento.objects.filter(
                    empresa=empresa, pago_em__gte=inicio_periodo
                ).aggregate(total=Sum("valor"))["total"]
                or 0,
                "dashboard_data": dashboard_data,
                "dashboard_range": self.request.GET.get("range") or "6m",
            }
        )
        return context


class DashboardDataView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        range_key = request.GET.get("range")
        start_value = request.GET.get("start")
        end_value = request.GET.get("end")
        start = parse_date(start_value) if start_value else None
        end = parse_date(end_value) if end_value else None
        data = build_dashboard_data(request.user, range_key=range_key, start=start, end=end)
        return JsonResponse(data)


class ClienteListView(EmpresaQuerysetMixin, ListView):
    model = Cliente
    paginate_by = 10
    template_name = "core/clientes_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(Q(nome__icontains=termo) | Q(telefone__icontains=termo) | Q(email__icontains=termo))
        return qs.order_by("nome")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_clientes"] = self.get_queryset().count()
        return context


class ClienteCreateView(EmpresaFormMixin, EmpresaQuerysetMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "core/form.html"
    success_url = reverse_lazy("clientes_list")
    extra_context = {"title": "Novo Cliente"}

    def form_valid(self, form):
        messages.success(self.request, "Cliente salvo com sucesso.")
        return super().form_valid(form)


class ClienteUpdateView(EmpresaFormMixin, EmpresaQuerysetMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "core/form.html"
    success_url = reverse_lazy("clientes_list")
    extra_context = {"title": "Editar Cliente"}

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado.")
        return super().form_valid(form)


class VeiculoListView(EmpresaQuerysetMixin, ListView):
    model = Veiculo
    paginate_by = 10
    template_name = "core/veiculos_list.html"

    def get_queryset(self):
        qs = super().get_queryset().select_related("cliente")
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(Q(placa__icontains=termo) | Q(cliente__nome__icontains=termo) | Q(modelo__icontains=termo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_veiculos"] = self.get_queryset().count()
        return context


class VeiculoCreateView(EmpresaFormMixin, EmpresaQuerysetMixin, CreateView):
    model = Veiculo
    form_class = VeiculoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("veiculos_list")
    extra_context = {"title": "Novo Veículo"}

    def form_valid(self, form):
        messages.success(self.request, "Veículo salvo com sucesso.")
        return super().form_valid(form)


class VeiculoUpdateView(EmpresaFormMixin, EmpresaQuerysetMixin, UpdateView):
    model = Veiculo
    form_class = VeiculoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("veiculos_list")
    extra_context = {"title": "Editar Veículo"}

    def form_valid(self, form):
        messages.success(self.request, "Veículo atualizado.")
        return super().form_valid(form)


class AgendaListView(EmpresaQuerysetMixin, FormMixin, ListView):
    model = Agenda
    form_class = AgendaForm
    template_name = "core/agenda_list.html"
    paginate_by = 10
    http_method_names = ["get", "post", "head", "options"]

    def _parse_date(self, value):
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return None

    def get_selected_date(self):
        if not hasattr(self, "_selected_date"):
            self._selected_date = self._parse_date(self.request.GET.get("data"))
        return self._selected_date

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        qs = self.get_search_queryset()
        selected_date = self.get_selected_date()
        if selected_date:
            qs = qs.filter(data_agendada=selected_date)
        return qs

    def get_search_queryset(self):
        if hasattr(self, "_search_queryset"):
            return self._search_queryset
        qs = super().get_queryset().select_related("cliente", "veiculo")
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(
                Q(cliente__nome__icontains=termo)
                | Q(veiculo__placa__icontains=termo)
                | Q(veiculo__modelo__icontains=termo)
            )
        self._search_queryset = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or self.get_form()
        selected_date = self.get_selected_date()
        if selected_date and not form.is_bound:
            form.initial.setdefault("data_agendada", selected_date)
        context.setdefault("form", form)

        hoje = timezone.now().date()
        default_month = selected_date.month if selected_date else hoje.month
        default_year = selected_date.year if selected_date else hoje.year

        def _parse_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        mes = _parse_int(self.request.GET.get("mes"), default_month)
        ano = _parse_int(self.request.GET.get("ano"), default_year)

        prev_month = 12 if mes == 1 else mes - 1
        prev_year = ano - 1 if mes == 1 else ano
        next_month = 1 if mes == 12 else mes + 1
        next_year = ano + 1 if mes == 12 else ano

        veiculos_qs = (
            Veiculo.objects.filter(empresa=self.request.user.empresa)
            .select_related("cliente")
            .only("id", "placa", "modelo", "cliente_id")
        )
        selected_events = []
        if selected_date:
            selected_events = list(
                self.get_search_queryset()
                .filter(data_agendada=selected_date)
                .select_related("cliente", "veiculo")
                .order_by("hora_agendada", "id")
            )
        eventos_fc = []
        for ag in self.get_search_queryset():
            all_day = not bool(ag.hora_agendada)
            start_value = (
                datetime.combine(ag.data_agendada, ag.hora_agendada).isoformat()
                if ag.hora_agendada
                else ag.data_agendada.isoformat()
            )
            eventos_fc.append(
                {
                    "id": ag.id,
                    "title": f"{ag.cliente.nome} - {ag.cliente.telefone}",
                    "start": start_value,
                    "allDay": all_day,
                    "extendedProps": {
                        "cliente": ag.cliente.nome,
                        "veiculo": f"{ag.veiculo.placa} - {ag.veiculo.modelo}",
                        "tipo": ag.get_tipo_display(),
                        "observacoes": ag.observacoes or "",
                        "hora": ag.hora_agendada.isoformat(timespec="minutes") if ag.hora_agendada else "",
                    },
                }
            )
        context.update(
            {
                "current_month": mes,
                "current_year": ano,
                "prev_month": prev_month,
                "prev_year": prev_year,
                "next_month": next_month,
                "next_year": next_year,
                "selected_date": selected_date,
                "selected_events": selected_events,
                "veiculos_json": json.dumps(
                    list(veiculos_qs.values("id", "placa", "modelo", "cliente_id"))
                ),
                "eventos_fc_json": json.dumps(eventos_fc, default=str),
            }
        )
        context["can_delete_agenda"] = self.request.user.has_perm("core.delete_agenda")
        return context

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = self.get_form()
        if form.is_valid():
            agenda = form.save(commit=False)
            agenda.empresa = request.user.empresa
            agenda.save()
            messages.success(request, "Agendamento criado.")
            return redirect("agenda")
        return self.render_to_response(self.get_context_data(form=form))


class AgendaMoveView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.empresa:
            return JsonResponse({"error": "Empresa não encontrada."}, status=400)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Dados inválidos."}, status=400)

        agenda_id = payload.get("id")
        date_str = payload.get("date")
        time_str = payload.get("time")
        all_day = bool(payload.get("allDay"))

        if not agenda_id or not date_str:
            return JsonResponse({"error": "Dados incompletos."}, status=400)

        try:
            agenda = Agenda.objects.get(pk=agenda_id, empresa=request.user.empresa)
        except Agenda.DoesNotExist:
            return JsonResponse({"error": "Agendamento não encontrado."}, status=404)

        nova_data = parse_date(date_str)
        if not nova_data:
            return JsonResponse({"error": "Data inválida."}, status=400)

        nova_hora = None
        if not all_day and time_str:
            try:
                nova_hora = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                return JsonResponse({"error": "Hora inválida."}, status=400)

        agenda.data_agendada = nova_data
        agenda.hora_agendada = nova_hora
        try:
            agenda.save(update_fields=["data_agendada", "hora_agendada"])
        except IntegrityError:
            return JsonResponse(
                {"error": "Conflito: já existe um agendamento para esse cliente/veículo nesse dia/horário."},
                status=400,
            )
        return JsonResponse({"ok": True})


class AgendaQuickCreateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        empresa = getattr(request.user, "empresa", None)
        if not empresa:
            return JsonResponse({"error": "Empresa não encontrada."}, status=400)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Dados inválidos."}, status=400)

        nome = (payload.get("cliente_nome") or "").strip()
        telefone = (payload.get("telefone") or "").strip()
        placa = (payload.get("placa") or "").strip().upper()
        modelo = (payload.get("modelo") or "").strip()
        veiculo_tipo = payload.get("veiculo_tipo") or Veiculo.Tipo.CARRO
        tipo_agenda = payload.get("tipo") or Agenda.Tipo.NOTA
        obs = (payload.get("observacoes") or "").strip()
        data_str = payload.get("data")
        hora_str = payload.get("hora")

        if not nome or not data_str or not hora_str:
            return JsonResponse({"error": "Informe nome, data e hora."}, status=400)

        data = parse_date(data_str)
        if not data:
            return JsonResponse({"error": "Data inválida."}, status=400)

        try:
            hora = datetime.strptime(hora_str, "%H:%M").time()
        except ValueError:
            return JsonResponse({"error": "Hora inválida."}, status=400)

        if veiculo_tipo not in Veiculo.Tipo.values:
            veiculo_tipo = Veiculo.Tipo.CARRO
        if tipo_agenda not in Agenda.Tipo.values:
            tipo_agenda = Agenda.Tipo.NOTA

        telefone_final = telefone or "Não informado"
        modelo_final = modelo or "Sem modelo"

        cliente, _ = Cliente.objects.get_or_create(
            empresa=empresa,
            nome=nome,
            defaults={
                "telefone": telefone_final,
                "email": "",
                "documento": "",
                "cep": "",
                "rua": "",
                "numero": "",
                "bairro": "",
                "cidade": "",
            },
        )

        if not placa:
            placa = f"TEMP-{cliente.id}"
        placa = placa[:10]

        veiculo_existente = Veiculo.objects.filter(empresa=empresa, placa=placa).first()
        if veiculo_existente and veiculo_existente.cliente_id != cliente.id:
            return JsonResponse({"error": "Placa já vinculada a outro cliente. Edite o cadastro completo."}, status=400)

        if veiculo_existente:
            veiculo = veiculo_existente
        else:
            veiculo = Veiculo.objects.create(
                empresa=empresa,
                cliente=cliente,
                tipo=veiculo_tipo,
                placa=placa,
                marca="",
                modelo=modelo_final,
                ano="",
                cor="",
            )

        agenda = Agenda(
            empresa=empresa,
            cliente=cliente,
            veiculo=veiculo,
            data_agendada=data,
            hora_agendada=hora,
            tipo=tipo_agenda,
            observacoes=obs,
        )
        try:
            agenda.save()
        except IntegrityError:
            return JsonResponse(
                {"error": "Conflito: já existe um agendamento para esse cliente/veículo nesse dia/horário."},
                status=400,
            )

        start_value = (
            datetime.combine(agenda.data_agendada, agenda.hora_agendada).isoformat()
            if agenda.hora_agendada
            else agenda.data_agendada.isoformat()
        )
        event_json = {
            "id": agenda.id,
            "title": f"{agenda.cliente.nome} - {agenda.cliente.telefone}",
            "start": start_value,
            "allDay": not bool(agenda.hora_agendada),
            "extendedProps": {
                "cliente": agenda.cliente.nome,
                "veiculo": f"{agenda.veiculo.placa} - {agenda.veiculo.modelo}",
                "tipo": agenda.get_tipo_display(),
                "observacoes": agenda.observacoes or "",
                "hora": agenda.hora_agendada.isoformat(timespec="minutes") if agenda.hora_agendada else "",
            },
        }
        return JsonResponse({"ok": True, "event": event_json})


class AgendaDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.has_perm("core.delete_agenda"):
            raise PermissionDenied
        if not request.user.empresa:
            return JsonResponse({"error": "Empresa não encontrada."}, status=400)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Dados inválidos."}, status=400)
        agenda_id = payload.get("id")
        if not agenda_id:
            return JsonResponse({"error": "ID ausente."}, status=400)
        try:
            agenda = Agenda.objects.get(pk=agenda_id, empresa=request.user.empresa)
        except Agenda.DoesNotExist:
            return JsonResponse({"error": "Agendamento não encontrado."}, status=404)
        agenda.delete()
        return JsonResponse({"ok": True})


class ContatoSuporteView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Dados inválidos."}, status=400)

        nome = (payload.get("nome") or "").strip()
        email = (payload.get("email") or "").strip()
        mensagem = (payload.get("mensagem") or "").strip()

        if not nome or not email or not mensagem:
            return JsonResponse({"error": "Preencha nome, email e mensagem."}, status=400)

        api_key = getattr(settings, "RESEND_API_KEY", "")
        to_email = getattr(settings, "CONTACT_EMAIL", "alpsistemascg@gmail.com")
        from_email = getattr(settings, "EMAIL_FROM", "no-reply@alpsistemas.app")
        if not api_key:
            return JsonResponse({"error": "Serviço de email não configurado. Informe o suporte."}, status=500)

        body = (
            "Solicitação de ajuda no login:\n\n"
            f"Nome: {nome}\n"
            f"Email: {email}\n"
            f"Mensagem:\n{mensagem}\n"
        )
        api_url = "https://api.resend.com/emails"

        def _send_payload(sender):
            payload = {
                "from": sender,
                "to": [to_email],
                "subject": "Ajuda no acesso - Oficina",
                "text": body,
                "reply_to": email,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                return True

        def _parse_resend_error(exc):
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                return payload.get("message") or payload.get("error") or payload.get("statusText")
            except Exception:
                return None

        try:
            _send_payload(from_email)
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and settings.DEBUG:
                test_from = getattr(settings, "RESEND_TEST_FROM_EMAIL", "")
                if test_from and test_from != from_email:
                    try:
                        _send_payload(test_from)
                        return JsonResponse({"ok": True})
                    except urllib.error.HTTPError as retry_exc:
                        exc = retry_exc
            detail = _parse_resend_error(exc)
            return JsonResponse({"error": detail or f"Erro ao enviar: {exc.code}"}, status=500)
        except Exception:
            return JsonResponse({"error": "Erro de comunicação com o serviço de email."}, status=500)

        return JsonResponse({"ok": True})


class UsuarioListView(ManagerRequiredMixin, EmpresaQuerysetMixin, ListView):
    model = Usuario
    paginate_by = 10
    template_name = "core/usuarios_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(
                Q(username__icontains=termo)
                | Q(email__icontains=termo)
                | Q(first_name__icontains=termo)
                | Q(last_name__icontains=termo)
            )
        return qs.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = getattr(self.request.user, "empresa", None)
        if empresa:
            context["limite_usuarios"] = empresa.limite_funcionarios()
            context["limite_gerentes"] = empresa.limite_gerentes()
            context["usuarios_ativos"] = Usuario.objects.filter(empresa=empresa, is_active=True).count()
            context["gerentes_ativos"] = Usuario.objects.filter(
                empresa=empresa, is_active=True, is_manager=True
            ).count()
        return context


class UsuarioCreateView(ManagerRequiredMixin, CreateView):
    model = Usuario
    form_class = UsuarioCreateForm
    template_name = "core/usuarios_form.html"
    success_url = reverse_lazy("usuarios_list")
    extra_context = {"title": "Novo usuario"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Usuario criado.")
        return super().form_valid(form)


class UsuarioUpdateView(ManagerRequiredMixin, UpdateView):
    model = Usuario
    form_class = UsuarioUpdateForm
    template_name = "core/usuarios_form.html"
    success_url = reverse_lazy("usuarios_list")
    extra_context = {"title": "Editar usuario"}

    def get_queryset(self):
        return Usuario.objects.filter(empresa=self.request.user.empresa)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Usuario atualizado.")
        return super().form_valid(form)


class UsuarioDeactivateView(ManagerRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        usuario_id = kwargs.get("pk")
        try:
            usuario = Usuario.objects.get(pk=usuario_id, empresa=request.user.empresa)
        except Usuario.DoesNotExist:
            raise PermissionDenied
        if usuario.pk == request.user.pk:
            messages.error(request, "Nao e possivel desativar o proprio usuario.")
            return redirect("usuarios_list")
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        messages.success(request, "Usuario desativado.")
        return redirect("usuarios_list")


class FuncionarioListView(ManagerRequiredMixin, EmpresaQuerysetMixin, ListView):
    model = Funcionario
    paginate_by = 10
    template_name = "core/funcionarios_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(
                Q(nome__icontains=termo)
                | Q(email__icontains=termo)
                | Q(telefone__icontains=termo)
            )
        return qs.order_by("nome")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_funcionarios"] = self.get_queryset().count()
        return context


class FuncionarioCreateView(ManagerRequiredMixin, EmpresaFormMixin, CreateView):
    model = Funcionario
    form_class = FuncionarioForm
    template_name = "core/funcionarios_form.html"
    success_url = reverse_lazy("funcionarios_list")
    extra_context = {"title": "Novo funcionario"}

    def form_valid(self, form):
        messages.success(self.request, "Funcionario criado.")
        return super().form_valid(form)


class FuncionarioUpdateView(ManagerRequiredMixin, EmpresaFormMixin, EmpresaQuerysetMixin, UpdateView):
    model = Funcionario
    form_class = FuncionarioForm
    template_name = "core/funcionarios_form.html"
    success_url = reverse_lazy("funcionarios_list")
    extra_context = {"title": "Editar funcionario"}

    def form_valid(self, form):
        messages.success(self.request, "Funcionario atualizado.")
        return super().form_valid(form)


class ProdutoListView(EmpresaQuerysetMixin, ListView):
    model = Produto
    paginate_by = 10
    template_name = "core/produtos_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        termo = self.request.GET.get("q")
        if termo:
            qs = qs.filter(Q(nome__icontains=termo) | Q(codigo__icontains=termo))
        return qs.order_by("nome")


class ProdutoCreateView(EmpresaFormMixin, EmpresaQuerysetMixin, CreateView):
    model = Produto
    form_class = ProdutoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("produtos_list")
    extra_context = {"title": "Novo Produto"}

    def form_valid(self, form):
        messages.success(self.request, "Produto salvo com sucesso.")
        return super().form_valid(form)


class ProdutoUpdateView(EmpresaFormMixin, EmpresaQuerysetMixin, UpdateView):
    model = Produto
    form_class = ProdutoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("produtos_list")
    extra_context = {"title": "Editar Produto"}

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado.")
        return super().form_valid(form)


def exportar_produtos_csv(request):
    empresa = request.user.empresa
    qs = Produto.objects.filter(empresa=empresa)
    termo = request.GET.get("q")
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(codigo__icontains=termo))

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="produtos.csv"'
    writer = csv.writer(response)
    writer.writerow(["Nome", "Descrição", "Código", "Custo", "Preço", "Estoque"])
    for p in qs:
        writer.writerow(
            [
                p.nome,
                p.descricao,
                p.codigo,
                f"{p.custo or 0:.2f}" if p.custo is not None else "",
                f"{p.preco or 0:.2f}" if p.preco is not None else "",
                p.estoque_atual if p.estoque_atual is not None else "",
            ]
        )
    return response


class OrdemServicoListView(EmpresaQuerysetMixin, ListView):
    model = OrdemServico
    paginate_by = 10
    template_name = "core/os_list.html"

    def _parse_date(self, value):
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return None

    def _validate_periodo(self, inicio, fim):
        if inicio and fim and inicio > fim:
            if not getattr(self, "_range_error_shown", False):
                messages.error(self.request, "Data de início não pode ser maior que a data final.")
                self._range_error_shown = True
            return None, None
        return inicio, fim

    def get_queryset(self):
        qs = os_queryset_for_user(
            self.request.user,
            OrdemServico.objects.select_related("cliente", "veiculo", "responsavel", "executor"),
        )
        status = self.request.GET.get("status")
        inicio = self._parse_date(self.request.GET.get("inicio"))
        fim = self._parse_date(self.request.GET.get("fim"))
        inicio, fim = self._validate_periodo(inicio, fim)
        termo = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if inicio:
            qs = qs.filter(entrada_em__gte=inicio)
        if fim:
            qs = qs.filter(entrada_em__lte=fim)
        if termo:
            qs = qs.filter(Q(cliente__nome__icontains=termo) | Q(veiculo__placa__icontains=termo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = OrdemServico.Status.choices
        return context


class OrdemServicoCreateView(EmpresaFormMixin, EmpresaQuerysetMixin, CreateView):
    model = OrdemServico
    form_class = OrdemServicoForm
    template_name = "core/form.html"
    extra_context = {"title": "Nova Ordem de Serviço"}

    def get_success_url(self):
        messages.success(self.request, "Ordem de serviço criada.")
        return reverse("os_detail", args=[self.object.pk])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not form.instance.responsavel:
            form.instance.responsavel = self.request.user
        form.instance.criado_por = self.request.user
        actions = _apply_os_status_audit(form.instance, None, self.request.user)
        response = super().form_valid(form)
        criar_os_log(self.object, self.request.user, OrdemServicoLog.Acao.CRIAR)
        if form.instance.responsavel_id:
            criar_os_log(self.object, self.request.user, OrdemServicoLog.Acao.ATRIBUIR)
        for action in actions:
            criar_os_log(self.object, self.request.user, action)
        return response


class OrdemServicoUpdateView(EmpresaFormMixin, EmpresaQuerysetMixin, UpdateView):
    model = OrdemServico
    form_class = OrdemServicoForm
    template_name = "core/form.html"
    extra_context = {"title": "Editar Ordem de Serviço"}

    def get_queryset(self):
        return os_queryset_for_user(self.request.user)

    def get_success_url(self):
        messages.success(self.request, "Ordem de serviço atualizada.")
        return reverse("os_detail", args=[self.object.pk])

    def form_valid(self, form):
        previous_status = self.object.status
        previous_responsavel_id = self.object.responsavel_id
        actions = _apply_os_status_audit(form.instance, previous_status, self.request.user)
        response = super().form_valid(form)
        responsavel_changed = previous_responsavel_id != form.instance.responsavel_id
        if responsavel_changed and form.instance.responsavel_id:
            criar_os_log(self.object, self.request.user, OrdemServicoLog.Acao.ATRIBUIR)
        for action in actions:
            criar_os_log(self.object, self.request.user, action)
        if not actions and not responsavel_changed and previous_status == form.instance.status:
            criar_os_log(self.object, self.request.user, OrdemServicoLog.Acao.EDITAR)
        return response


class OrdemServicoDetailView(EmpresaQuerysetMixin, DetailView):
    model = OrdemServico
    template_name = "core/os_detail.html"

    def get_queryset(self):
        return os_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("item_form", OSItemForm(user=self.request.user))
        context.setdefault("pagamento_form", PagamentoForm(user=self.request.user))
        produtos = Produto.objects.filter(empresa=self.request.user.empresa).values("id", "preco", "nome", "descricao")
        context["produtos_info_json"] = json.dumps(
            {
                str(p["id"]): {
                    "preco": float(p["preco"] or 0),
                    "nome": p["nome"],
                    "descricao": p["descricao"] or "",
                }
                for p in produtos
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "add_item" in request.POST:
            item_form = OSItemForm(request.POST, user=request.user)
            pagamento_form = PagamentoForm(user=request.user)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.os = self.object
                item.empresa = request.user.empresa
                item.save()
                if item.produto and item.produto.estoque_atual is not None:
                    item.produto.estoque_atual = item.produto.estoque_atual - int(item.qtd)
                    item.produto.save(update_fields=["estoque_atual"])
                messages.success(request, "Item adicionado.")
                return redirect("os_detail", pk=self.object.pk)
        elif "add_pagamento" in request.POST:
            pagamento_form = PagamentoForm(request.POST, user=request.user)
            item_form = OSItemForm(user=request.user)
            if pagamento_form.is_valid():
                pagamento = pagamento_form.save(commit=False)
                pagamento.os = self.object
                pagamento.empresa = request.user.empresa
                pagamento.save()
                messages.success(request, "Pagamento registrado.")
                return redirect("os_detail", pk=self.object.pk)
        else:
            item_form = OSItemForm(user=request.user)
            pagamento_form = PagamentoForm(user=request.user)

        context = self.get_context_data(item_form=item_form, pagamento_form=pagamento_form)
        return self.render_to_response(context)


class OrdemServicoPdfView(LoginRequiredMixin, View):
    def get(self, request, pk):
        try:
            from weasyprint import HTML
        except ImportError:
            messages.error(
                request,
                "Para gerar PDF, instale a dependência weasyprint.",
            )
            return redirect("os_detail", pk=pk)

        os_obj = get_object_or_404(
            os_queryset_for_user(request.user)
            .select_related("cliente", "veiculo", "responsavel", "executor")
            .prefetch_related("itens", "pagamentos"),
            pk=pk,
        )
        empresa = os_obj.empresa or request.user.empresa
        def _logo_exists(company):
            if not company:
                return False
            checker = getattr(company, "logomarca_existe", None)
            if callable(checker):
                return checker()
            logo = getattr(company, "logomarca", None)
            if not logo:
                return False
            storage = getattr(logo, "storage", None) or default_storage
            try:
                return storage.exists(logo.name)
            except Exception:
                return False

        def _logo_url(company):
            if not company:
                return ""
            getter = getattr(company, "logomarca_url", None)
            if callable(getter):
                return getter() or ""
            logo = getattr(company, "logomarca", None)
            if not logo:
                return ""
            try:
                return logo.url
            except Exception:
                return ""

        logo_src = None
        logo_path = None
        if _logo_exists(empresa):
            try:
                logo_path = empresa.logomarca.path
            except (NotImplementedError, OSError, ValueError):
                logo_path = None
            data = None
            if logo_path:
                path = Path(logo_path)
                if path.exists():
                    try:
                        data = path.read_bytes()
                    except OSError:
                        data = None
            if data is None:
                try:
                    with empresa.logomarca.open("rb") as logo_file:
                        data = logo_file.read()
                except OSError:
                    data = None

            if data:
                try:
                    from PIL import Image
                except ImportError:
                    Image = None
                if Image:
                    try:
                        image = Image.open(BytesIO(data))
                        image = image.convert("RGBA")
                        image.thumbnail((600, 600))
                        buffer = BytesIO()
                        image.save(buffer, format="PNG", optimize=True)
                        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                        logo_src = f"data:image/png;base64,{encoded}"
                    except Exception:
                        logo_src = None
                if not logo_src:
                    mime_type = mimetypes.guess_type(empresa.logomarca.name or "")[0] or "image/png"
                    encoded = base64.b64encode(data).decode("ascii")
                    logo_src = f"data:{mime_type};base64,{encoded}"
            if not logo_src and logo_path:
                path = Path(logo_path)
                if path.exists():
                    logo_src = path.as_uri()
            if not logo_src:
                logo_src = _logo_url(empresa) or None

        context = {
            "object": os_obj,
            "empresa": empresa,
            "logo_src": logo_src,
            "gerado_em": timezone.now(),
        }
        html = render_to_string("core/os_pdf.html", context)
        pdf_file = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="os_{os_obj.id}.pdf"'
        return response


class CaixaView(ManagerRequiredMixin, EmpresaQuerysetMixin, TemplateView):
    template_name = "core/caixa.html"

    def _parse_date(self, value, default):
        if not value:
            return default
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return default

    def get_periodo(self):
        hoje = timezone.now().date()
        primeiro_dia = hoje.replace(day=1)
        inicio = self._parse_date(self.request.GET.get("inicio"), primeiro_dia)
        fim = self._parse_date(self.request.GET.get("fim"), hoje)
        if self.request.GET.get("inicio") and self.request.GET.get("fim") and inicio > fim:
            if not getattr(self, "_range_error_shown", False):
                messages.error(self.request, "Data de início não pode ser maior que a data final.")
                self._range_error_shown = True
            inicio = primeiro_dia
            fim = hoje
        return inicio, fim

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inicio, fim = self.get_periodo()
        empresa = self.request.user.empresa
        entradas = Pagamento.objects.filter(empresa=empresa, pago_em__gte=inicio, pago_em__lte=fim)
        saidas = Despesa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        total_entradas = entradas.aggregate(total=Sum("valor"))["total"] or 0
        total_saidas = saidas.aggregate(total=Sum("valor"))["total"] or 0
        context.update(
            {
                "inicio": inicio,
                "fim": fim,
                "entradas": entradas,
                "saidas": saidas,
                "total_entradas": total_entradas,
                "total_saidas": total_saidas,
                "saldo": total_entradas - total_saidas,
                "despesa_form": kwargs.get("despesa_form") or DespesaForm(user=self.request.user),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = DespesaForm(request.POST, user=request.user)
        if form.is_valid():
            despesa = form.save(commit=False)
            despesa.empresa = request.user.empresa
            despesa.save()
            messages.success(request, "Despesa registrada.")
            return redirect("caixa")
        context = self.get_context_data(despesa_form=form)
        return self.render_to_response(context)


class CaixaGraficosView(ManagerRequiredMixin, TemplateView):
    template_name = "core/caixa_graficos.html"

    def _aggregate(self, qs, field, kind, start=None):
        trunc_map = {
            "day": TruncDate(field),
            "month": TruncMonth(field),
            "year": TruncYear(field),
        }
        if start:
            qs = qs.filter(**{f"{field}__gte": start})
        return (
            qs.annotate(period=trunc_map[kind])
            .values("period")
            .annotate(total=Sum("valor"))
            .order_by("period")
        )

    def _merge(self, entradas, saidas, label_fmt):
        data = {}
        for e in entradas:
            data[e["period"]] = {
                "period": e["period"],
                "label": label_fmt(e["period"]),
                "entradas": e["total"] or 0,
                "saidas": 0,
            }
        for s in saidas:
            if s["period"] in data:
                data[s["period"]]["saidas"] = s["total"] or 0
            else:
                data[s["period"]] = {
                    "period": s["period"],
                    "label": label_fmt(s["period"]),
                    "entradas": 0,
                    "saidas": s["total"] or 0,
                }
        items = sorted(data.values(), key=lambda d: d["period"])
        max_total = max([d["entradas"] for d in items] + [d["saidas"] for d in items] + [1])
        for d in items:
            d["entrada_pct"] = (d["entradas"] / max_total) * 100 if max_total else 0
            d["saida_pct"] = (d["saidas"] / max_total) * 100 if max_total else 0
        return items

    def _serialize(self, items):
        return [
            {
                "label": i["label"],
                "iso": i["period"].isoformat() if hasattr(i["period"], "isoformat") else str(i["period"]),
                "entradas": float(i["entradas"] or 0),
                "saidas": float(i["saidas"] or 0),
                "saldo": float((i["entradas"] or 0) - (i["saidas"] or 0)),
            }
            for i in items
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        today = timezone.now().date()
        pagamentos = Pagamento.objects.filter(empresa=empresa)
        despesas = Despesa.objects.filter(empresa=empresa)

        dias = self._merge(
            self._aggregate(pagamentos, "pago_em", "day", today - timezone.timedelta(days=29)),
            self._aggregate(despesas, "data", "day", today - timezone.timedelta(days=29)),
            lambda d: d.strftime("%d/%m"),
        )
        meses = self._merge(
            self._aggregate(pagamentos, "pago_em", "month", today.replace(day=1) - timezone.timedelta(days=150)),
            self._aggregate(despesas, "data", "month", today.replace(day=1) - timezone.timedelta(days=150)),
            lambda d: d.strftime("%b/%Y"),
        )
        anos = self._merge(
            self._aggregate(pagamentos, "pago_em", "year", today.replace(month=1, day=1) - timezone.timedelta(days=365 * 2)),
            self._aggregate(despesas, "data", "year", today.replace(month=1, day=1) - timezone.timedelta(days=365 * 2)),
            lambda d: d.strftime("%Y"),
        )

        formas = (
            pagamentos.values("forma_pagamento")
            .annotate(total=Sum("valor"))
            .order_by("forma_pagamento")
        )

        context.update(
            {
                "dias": dias,
                "meses": meses,
                "anos": anos,
                "formas": formas,
                "chart_data": {
                    "dia": self._serialize(dias),
                    "mes": self._serialize(meses),
                    "ano": self._serialize(anos),
                    "formas": [
                        {"forma": f["forma_pagamento"] or "Não informado", "total": float(f["total"] or 0)}
                        for f in formas
                    ],
                },
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = DespesaForm(request.POST, user=request.user)
        if form.is_valid():
            despesa = form.save(commit=False)
            despesa.empresa = request.user.empresa
            despesa.save()
            messages.success(request, "Despesa registrada.")
            return redirect(
                f"{reverse('caixa')}?inicio={request.GET.get('inicio','')}&fim={request.GET.get('fim','')}"
            )
        context = self.get_context_data(despesa_form=form)
        return self.render_to_response(context)


class ManualView(LoginRequiredMixin, TemplateView):
    template_name = "core/manual.html"


class RelatoriosView(ManagerRequiredMixin, TemplateView):
    template_name = "core/relatorios.html"

    def _parse_date(self, value):
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return None

    def _validar_periodo(self, inicio, fim):
        if inicio and fim and inicio > fim:
            return False
        return True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        inicio = self._parse_date(self.request.GET.get("inicio")) or timezone.now().date() - timedelta(days=30)
        fim = self._parse_date(self.request.GET.get("fim")) or timezone.now().date()
        if not self._validar_periodo(inicio, fim):
            messages.error(self.request, "Data de início não pode ser maior que a data final.")
            inicio, fim = (timezone.now().date() - timedelta(days=30), timezone.now().date())
        ordens = OrdemServico.objects.filter(empresa=empresa, entrada_em__gte=inicio, entrada_em__lte=fim)
        pagamentos = Pagamento.objects.filter(empresa=empresa, pago_em__gte=inicio, pago_em__lte=fim)
        despesas = Despesa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        os_por_status = {label: ordens.filter(status=value).count() for value, label in OrdemServico.Status.choices}
        clientes_em_aberto = sorted({os.cliente for os in ordens if os.saldo > 0}, key=lambda c: c.nome)
        pendencias = [
            {"cliente": os.cliente, "telefone": os.cliente.telefone, "os_id": os.id, "saldo": os.saldo}
            for os in ordens
            if os.saldo > 0
        ]
        context.update(
            {
                "inicio": inicio,
                "fim": fim,
                "ordens": ordens,
                "os_por_status": os_por_status,
                "faturamento": pagamentos.aggregate(total=Sum("valor"))["total"] or 0,
                "total_despesas": despesas.aggregate(total=Sum("valor"))["total"] or 0,
                "clientes_em_aberto": clientes_em_aberto,
                "pendencias": pendencias,
            }
        )
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CustomLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm


class AutoCadastroView(FormMixin, TemplateView):
    template_name = "registration/signup.html"
    form_class = AutoCadastroForm
    success_url = reverse_lazy("login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_invalid(self, form):
        # Remove mensagens antigas para evitar confusao quando o formulario falha.
        list(messages.get_messages(self.request))
        for error in form.non_field_errors():
            messages.error(self.request, error)
        for field, errors in form.errors.items():
            if field == "__all__":
                continue
            label = form.fields.get(field).label if field in form.fields else field
            for error in errors:
                messages.error(self.request, f"{label}: {error}")
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        user = form.save()
        messages.success(
            self.request,
            "Cadastro recebido. Assim que o pagamento for confirmado, liberaremos o acesso ao sistema "
            "e enviaremos uma notificação por e-mail ou WhatsApp.",
        )
        enviado, erro = _notify_nova_liberacao(user.empresa, user)
        if not enviado:
            messages.warning(
                self.request,
                "Cadastro recebido, mas não foi possível enviar o e-mail de notificação. "
                "Verifique as configurações de e-mail.",
            )
        return super().form_valid(form)


class EmpresaRenovacaoView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        empresa = getattr(request.user, "empresa", None)
        if not empresa:
            messages.error(request, "Empresa não encontrada.")
            return redirect("dashboard")
        periodo = request.POST.get("periodo")
        choices = {value for value, _ in Empresa.PlanoPeriodo.choices}
        if periodo not in choices:
            messages.error(request, "Selecione um período válido.")
            return redirect(request.META.get("HTTP_REFERER", "dashboard"))
        empresa.renovacao_periodo = periodo
        empresa.renovacao_solicitada_em = timezone.now()
        empresa.save(update_fields=["renovacao_periodo", "renovacao_solicitada_em"])
        messages.success(request, "Solicitação de renovação enviada. Confirmação após o pagamento.")
        return redirect(request.META.get("HTTP_REFERER", "dashboard"))


class PasswordRecoveryView(FormMixin, TemplateView):
    template_name = "registration/password_recovery.html"
    form_class = PasswordRecoveryForm
    success_url = reverse_lazy("login")

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        from .forms import _send_resend_email

        identificador = form.cleaned_data["identificador"]
        digits = re.sub(r"\D", "", identificador)
        user = None
        if "@" in identificador:
            user = Usuario.objects.filter(email__iexact=identificador).first()
            if not user:
                user = Usuario.objects.filter(email_recuperacao__iexact=identificador).first()
        else:
            if digits:
                user = Usuario.objects.filter(telefone_recuperacao__icontains=digits).first()
                if not user:
                    user = Usuario.objects.filter(empresa__telefone__icontains=digits).first()

        if not user:
            form.add_error("identificador", "Nenhuma conta encontrada com esse e-mail ou telefone.")
            return self.form_invalid(form)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = self.request.build_absolute_uri(reverse("password_reset_confirm", args=[uid, token]))
        destino = user.email_recuperacao or user.email
        subject = "Recuperacao de senha - SaaS Gestao de Oficina"
        body = (
            "Recebemos uma solicitacao de recuperacao de senha.\n\n"
            f"Para definir uma nova senha, acesse o link abaixo:\n{reset_url}\n\n"
            "Se voce nao solicitou, ignore esta mensagem."
        )

        email_sent = False
        if destino:
            enviado, erro = _send_resend_email(subject, body, destino)
            if not enviado:
                messages.error(
                    self.request,
                    f"Nao foi possivel enviar o email de recuperacao. {erro or ''}".strip(),
                )
                return self.form_invalid(form)
            email_sent = True

        if "@" not in identificador and digits:
            phone_digits = re.sub(r"\D", "", user.telefone_recuperacao or "")
            if not phone_digits:
                phone_digits = re.sub(r"\D", "", user.empresa.telefone or "")
            if phone_digits and not phone_digits.startswith("55") and len(phone_digits) in (10, 11):
                phone_digits = f"55{phone_digits}"
            whatsapp_link = ""
            if phone_digits:
                whatsapp_text = (
                    "Recebemos sua solicitacao de recuperacao de senha. "
                    f"Para definir uma nova senha, acesse: {reset_url}"
                )
                whatsapp_link = (
                    f"https://wa.me/{phone_digits}?text={urllib.parse.quote(whatsapp_text)}"
                )
            if whatsapp_link:
                context = self.get_context_data(form=form)
                context.update(
                    {
                        "whatsapp_link": whatsapp_link,
                        "email_sent": email_sent,
                    }
                )
                if email_sent:
                    messages.success(
                        self.request,
                        "Enviamos um e-mail com as instruções para recuperar sua senha.",
                    )
                return self.render_to_response(context)

        if email_sent:
            messages.success(
                self.request,
                "Enviamos um e-mail com as instruções para recuperar sua senha.",
            )
        else:
            form.add_error("identificador", "Nenhum e-mail ou telefone cadastrado para recuperar a senha.")
            return self.form_invalid(form)

        return super().form_valid(form)


class EmpresaAprovacaoView(SuperuserRequiredMixin, TemplateView):
    template_name = "core/empresas_aprovacao.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresas = Empresa.objects.all().order_by("-criado_em")
        context["empresas"] = empresas
        context["pendentes"] = empresas.filter(pagamento_confirmado=False).count()
        context["planos"] = Empresa.Plano.choices
        context["periodos"] = Empresa.PlanoPeriodo.choices
        context["whatsapp_message"] = (
            "Seu acesso ao sistema foi liberado. "
            "Link de acesso: https://alpoficinas.com.br/"
        )
        return context

    def post(self, request, *args, **kwargs):
        empresa_id = request.POST.get("empresa_id")
        empresa = get_object_or_404(Empresa, pk=empresa_id)
        was_aprovado = empresa.pagamento_confirmado
        aprovado = request.POST.get("pagamento_confirmado") == "on"
        plano = request.POST.get("plano")
        plano_periodo = request.POST.get("plano_periodo")
        confirmar_renovacao = request.POST.get("confirmar_renovacao") == "on"

        plano_choices = {value for value, _ in Empresa.Plano.choices}
        periodo_choices = {value for value, _ in Empresa.PlanoPeriodo.choices}
        if plano in plano_choices:
            empresa.plano = plano
        if plano_periodo in periodo_choices:
            empresa.plano_periodo = plano_periodo

        empresa.pagamento_confirmado = aprovado
        if confirmar_renovacao and empresa.renovacao_periodo:
            if not empresa.pagamento_confirmado:
                messages.warning(request, "Confirme o pagamento antes de renovar o plano.")
            else:
                empresa.plano_periodo = plano_periodo if plano_periodo in periodo_choices else empresa.renovacao_periodo
                empresa.plano_atualizado_em = timezone.now()
                empresa.renovacao_periodo = ""
                empresa.renovacao_solicitada_em = None
                messages.success(request, f"Renovação confirmada para {empresa.nome}.")
        empresa.save()
        if aprovado:
            messages.success(request, f"Acesso liberado para {empresa.nome}.")
            if not was_aprovado:
                usuario = empresa.usuarios.order_by("date_joined").first()
                if not usuario:
                    messages.warning(request, "Nao foi encontrado usuario para esta empresa.")
                    return redirect("empresas_aprovacao")
                senha = empresa.senha_temporaria
                if not senha:
                    senha = get_random_string(12)
                    usuario.set_password(senha)
                    usuario.save(update_fields=["password"])
                enviado, erro = _notify_aprovacao_acesso(empresa, usuario, senha)
                if enviado:
                    if empresa.senha_temporaria:
                        empresa.senha_temporaria = ""
                        empresa.save(update_fields=["senha_temporaria"])
                else:
                    messages.warning(
                        request,
                        f"Email de acesso nao enviado. {erro or 'Verifique RESEND_API_KEY e EMAIL_FROM.'}",
                    )
        else:
            messages.warning(request, f"Acesso bloqueado para {empresa.nome}.")
        return redirect("empresas_aprovacao")


class EmpresaUpdateView(ManagerRequiredMixin, UpdateView):
    model = Empresa
    form_class = EmpresaUpdateForm
    template_name = "core/empresa_form.html"
    success_url = reverse_lazy("dashboard")

    def get_object(self, queryset=None):
        return get_object_or_404(Empresa, pk=self.request.user.empresa_id)

    def form_valid(self, form):
        messages.success(self.request, "Dados da empresa atualizados.")
        return super().form_valid(form)


def logout_view(request):
    """Permite logout via GET para evitar erro 405 em links simples."""
    logout(request)
    messages.success(request, "Sessão encerrada.")
    return redirect("login")
