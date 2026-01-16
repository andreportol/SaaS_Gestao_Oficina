import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Empresa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150)),
                ('cnpj_cpf', models.CharField(blank=True, max_length=20)),
                ('telefone', models.CharField(blank=True, max_length=20)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Usuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(
                    error_messages={'unique': 'A user with that username already exists.'},
                    help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
                    max_length=150,
                    unique=True,
                    validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                    verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('is_manager', models.BooleanField(default=False)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='usuarios', to='core.empresa')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='usuario_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='usuario_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150)),
                ('telefone', models.CharField(max_length=30)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('documento', models.CharField(blank=True, max_length=30)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clientes', to='core.empresa')),
            ],
            options={
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='Produto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150)),
                ('codigo', models.CharField(blank=True, max_length=50)),
                ('custo', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ('preco', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('estoque_atual', models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='produtos', to='core.empresa')),
            ],
            options={
                'ordering': ['nome'],
                'unique_together': {('empresa', 'nome')},
            },
        ),
        migrations.CreateModel(
            name='Veiculo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('MOTO', 'Moto'), ('CARRO', 'Carro'), ('CAMINHAO', 'Caminhão')], max_length=10)),
                ('placa', models.CharField(max_length=10)),
                ('marca', models.CharField(max_length=50)),
                ('modelo', models.CharField(max_length=50)),
                ('ano', models.PositiveIntegerField(blank=True, null=True)),
                ('cor', models.CharField(blank=True, max_length=30)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='veiculos', to='core.cliente')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='veiculos', to='core.empresa')),
            ],
            options={
                'ordering': ['placa'],
                'unique_together': {('empresa', 'placa')},
            },
        ),
        migrations.CreateModel(
            name='FormaPagamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=60)),
                ('ativo', models.BooleanField(default=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='formas_pagamento', to='core.empresa')),
            ],
            options={
                'ordering': ['nome'],
                'unique_together': {('empresa', 'nome')},
            },
        ),
        migrations.CreateModel(
            name='OrdemServico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('ABERTA', 'Aberta'), ('EXECUCAO', 'Em Execução'), ('AGUARDANDO_PECA', 'Aguardando Peça'), ('FINALIZADA', 'Finalizada'), ('ENTREGUE', 'Entregue'), ('CANCELADA', 'Cancelada')], default='ABERTA', max_length=20)),
                ('entrada_em', models.DateField(default=django.utils.timezone.now)),
                ('previsao_entrega', models.DateField(blank=True, null=True)),
                ('problema', models.TextField()),
                ('diagnostico', models.TextField(blank=True)),
                ('mao_de_obra', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('desconto', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('observacoes', models.TextField(blank=True)),
                ('anexo', models.FileField(blank=True, null=True, upload_to='anexos/', validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])])),
                ('total_cache', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ordens_servico', to='core.cliente')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ordens_servico', to='core.empresa')),
                ('veiculo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ordens_servico', to='core.veiculo')),
            ],
            options={
                'ordering': ['-entrada_em', '-id'],
            },
        ),
        migrations.CreateModel(
            name='OSItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descricao', models.CharField(max_length=255)),
                ('qtd', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('valor_unitario', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('subtotal', models.DecimalField(blank=True, decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='os_itens', to='core.empresa')),
                ('os', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='core.ordemservico')),
                ('produto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='itens', to='core.produto')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='Pagamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('pago_em', models.DateField(default=django.utils.timezone.now)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagamentos', to='core.empresa')),
                ('forma_pagamento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.formapagamento')),
                ('os', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagamentos', to='core.ordemservico')),
            ],
            options={
                'ordering': ['-pago_em', '-id'],
            },
        ),
        migrations.CreateModel(
            name='Despesa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descricao', models.CharField(max_length=200)),
                ('valor', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('data', models.DateField(default=django.utils.timezone.now)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='despesas', to='core.empresa')),
            ],
            options={
                'ordering': ['-data', '-id'],
            },
        ),
    ]
