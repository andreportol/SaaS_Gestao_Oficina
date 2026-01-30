FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libglib2.0-0 \
    libgobject-2.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libffi-dev \
    shared-mime-info \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8080

CMD ["bash", "-lc", "gunicorn ProjetoOficina.wsgi:application --bind 0.0.0.0:${PORT:-8080} --log-file -"]
