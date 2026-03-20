FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS server-builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_SYSTEM_PYTHON=1

# Prefect server only needs the core dependencies
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev

# Set path for prefect binary
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 4200

CMD ["prefect", "server", "start", "--host", "0.0.0.0"]