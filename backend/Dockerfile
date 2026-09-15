FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 10001 relaymaid
WORKDIR /app

COPY --from=builder --chown=relaymaid:relaymaid /app/.venv /app/.venv
COPY --from=builder --chown=relaymaid:relaymaid /app/src /app/src

USER relaymaid
EXPOSE 8000

CMD ["uvicorn", "relaymaid.main:app", "--host", "0.0.0.0", "--port", "8000"]
