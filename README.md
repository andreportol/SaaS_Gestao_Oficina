# ProjetoOficina - SaaS para Oficinas

Sistema Django para gestao de oficinas (motos, carros e caminhoes). Inclui clientes, veiculos, OS com itens e pagamentos, caixa e relatorios. Multi-tenant por empresa.

## Stack
- Django 4.2
- Postgres
- Bootstrap 5
- Gunicorn + WhiteNoise (deploy)

## Funcionalidades
- Empresas e usuarios com permissao de gerente
- Clientes e veiculos
- Ordens de servico com itens, pagamentos, status e saldo
- Caixa (entradas x despesas) e relatorios
- Dashboard com graficos

## Rodando localmente (sem Docker)
1. Crie o venv e instale dependencias:
```
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r app\requirements.txt
```
2. Configure o arquivo `app/.env` (veja `app/.env.example`).
3. Rode as migracoes:
```
python app\manage.py migrate
```
4. Crie um usuario admin:
```
python app\manage.py createsuperuser
```
5. Suba o servidor:
```
python app\manage.py runserver
```

## Rodando com Docker
1. Copie o arquivo de variaveis: `cp app/.env.example app/.env`
2. Suba os servicos:
```
docker compose up --build
```
3. (Opcional) Seed:
```
docker compose exec web python manage.py seed_demo
```

## Testes
```
python app\manage.py test
```

## Deploy no Railway
1. Variaveis obrigatorias:
   - `SECRET_KEY`
   - `DEBUG=False`
   - `ALLOWED_HOSTS` (ex: `seu-app.up.railway.app`)
   - `CSRF_TRUSTED_ORIGINS` (ex: `https://seu-app.up.railway.app`)
   - `DATABASE_URL` (Railway Postgres)
   - `RESEND_API_KEY`
   - `EMAIL_FROM` (ex: `ALP Oficinas <no-reply@alpoficinas.com.br>`)
   - `CONTACT_EMAIL` (destino das notificacoes)
2. Comandos apos o deploy:
```
python app/manage.py migrate
python app/manage.py collectstatic --noinput
```

## Observacoes
- Uploads (logomarca) precisam de storage persistente em producao.
