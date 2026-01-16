from django.urls import path

from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('clientes/', views.ClienteListView.as_view(), name='clientes_list'),
    path('clientes/novo/', views.ClienteCreateView.as_view(), name='clientes_create'),
    path('clientes/<int:pk>/editar/', views.ClienteUpdateView.as_view(), name='clientes_update'),
    path('veiculos/', views.VeiculoListView.as_view(), name='veiculos_list'),
    path('veiculos/novo/', views.VeiculoCreateView.as_view(), name='veiculos_create'),
    path('veiculos/<int:pk>/editar/', views.VeiculoUpdateView.as_view(), name='veiculos_update'),
    path('agenda/', views.AgendaListView.as_view(), name='agenda'),
    path('agenda/mover/', views.AgendaMoveView.as_view(), name='agenda_move'),
    path('agenda/rapido/', views.AgendaQuickCreateView.as_view(), name='agenda_quick_create'),
    path('agenda/deletar/', views.AgendaDeleteView.as_view(), name='agenda_delete'),
    path('contato-suporte/', views.ContatoSuporteView.as_view(), name='contato_suporte'),
    path('usuarios/', views.UsuarioListView.as_view(), name='usuarios_list'),
    path('usuarios/novo/', views.UsuarioCreateView.as_view(), name='usuarios_create'),
    path('usuarios/<int:pk>/editar/', views.UsuarioUpdateView.as_view(), name='usuarios_update'),
    path('usuarios/<int:pk>/desativar/', views.UsuarioDeactivateView.as_view(), name='usuarios_deactivate'),
    path('produtos/', views.ProdutoListView.as_view(), name='produtos_list'),
    path('produtos/novo/', views.ProdutoCreateView.as_view(), name='produtos_create'),
    path('produtos/exportar/', views.exportar_produtos_csv, name='produtos_export'),
    path('produtos/<int:pk>/editar/', views.ProdutoUpdateView.as_view(), name='produtos_update'),
    path('os/', views.OrdemServicoListView.as_view(), name='os_list'),
    path('os/nova/', views.OrdemServicoCreateView.as_view(), name='os_create'),
    path('os/<int:pk>/', views.OrdemServicoDetailView.as_view(), name='os_detail'),
    path('os/<int:pk>/editar/', views.OrdemServicoUpdateView.as_view(), name='os_update'),
    path('caixa/', views.CaixaView.as_view(), name='caixa'),
    path('caixa/graficos/', views.CaixaGraficosView.as_view(), name='caixa_graficos'),
    path('relatorios/', views.RelatoriosView.as_view(), name='relatorios'),
]
