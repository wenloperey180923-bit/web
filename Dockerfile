# Despliegue en Render de la versión Python (Flask).
# La versión PHP anterior se conserva en Dockerfile.php.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render indica el puerto en la variable PORT.
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 4 --preload --timeout 120
