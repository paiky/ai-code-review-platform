FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SERVER_PORT=8090

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend-python/pyproject.toml /app/pyproject.toml
RUN python -m pip install --upgrade pip \
    && python -c '\
import subprocess, sys, tomllib; \
config = tomllib.loads(open("pyproject.toml", encoding="utf-8").read()); \
subprocess.check_call([sys.executable, "-m", "pip", "install", *config["build-system"]["requires"], *config["project"]["dependencies"]])'

COPY backend-python/app /app/app
COPY backend-python/migrations /app/migrations

ARG REVIEW_RELEASE_SHA
LABEL org.opencontainers.image.revision=${REVIEW_RELEASE_SHA}
RUN install -d /usr/local/share/ai-review \
    && printf '%s\n' "$REVIEW_RELEASE_SHA" > /usr/local/share/ai-review/release-sha \
    && chmod 444 /usr/local/share/ai-review/release-sha

# V58 onward was released with LF. Earlier migration checksums use the original bytes.
RUN set -e; \
    for migration in migrations/bootstrap_sql/V*__*.sql; do \
        version="${migration##*/V}"; \
        if [ "${version%%__*}" -ge 58 ]; then sed -i 's/\r$//' "$migration"; fi; \
    done; \
    python -m pip install --no-deps --no-build-isolation .

EXPOSE 8090

CMD ["sh", "-c", "python -m app.migrate && exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${SERVER_PORT:-8090}"]
