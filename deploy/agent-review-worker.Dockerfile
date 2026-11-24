FROM node:20-bookworm-slim AS claude-code

ARG CLAUDE_CODE_VERSION=2.1.112

RUN npm install --global "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/agent-review \
    DISABLE_AUTOUPDATER=1 \
    DISABLE_TELEMETRY=1 \
    DISABLE_ERROR_REPORTING=1 \
    DISABLE_BUG_COMMAND=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent-review \
    && pip install --no-cache-dir "httpx>=0.27.0"

COPY --from=claude-code /usr/local/bin/node /usr/local/bin/node
COPY --from=claude-code /usr/local/lib/node_modules/@anthropic-ai/claude-code /usr/local/lib/node_modules/@anthropic-ai/claude-code
RUN ln -s /usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js /usr/local/bin/claude
RUN pip install --no-cache-dir "pydantic>=2,<3"

WORKDIR /opt/agent-review
COPY backend-python/app/__init__.py /opt/agent-review/app/__init__.py
COPY backend-python/app/agent_review_spike /opt/agent-review/app/agent_review_spike
COPY backend-python/app/agent_review/__init__.py /opt/agent-review/app/agent_review/__init__.py
COPY backend-python/app/agent_review/worker.py /opt/agent-review/app/agent_review/worker.py
COPY backend-python/app/agent_review/schemas.py /opt/agent-review/app/agent_review/schemas.py
COPY backend-python/app/review_prompt_metadata.py /opt/agent-review/app/review_prompt_metadata.py
COPY backend-python/app/code_quality/__init__.py backend-python/app/code_quality/prompt.py /opt/agent-review/app/code_quality/

USER 10001:10001
RUN python3 -c "import app.agent_review.worker"
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-m", "app.agent_review.worker"]
