FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SERVER_PORT=8080

WORKDIR /app

COPY backend-python/pyproject.toml /app/pyproject.toml
COPY backend-python/app /app/app
COPY backend-python/migrations /app/migrations

RUN python -m pip install --upgrade pip \
    && python -m pip install .

EXPOSE 8080

CMD ["sh", "-c", "python -m app.migrate && exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${SERVER_PORT:-8080}"]
