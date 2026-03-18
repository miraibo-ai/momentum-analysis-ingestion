# Use the official uv image for the build stage
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# 1. Setup working directory
WORKDIR /app

# 2. Optimization: Enable bytecode compilation and use 'copy' mode
# (Hardlinks don't work across Docker layers)
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# 3. Cache dependencies: Copy only the lockfile and project metadata first
# This layer is ONLY rebuilt if your dependencies change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# 4. Copy the rest of your Miraiibo source code
ADD . /app

# 5. Final sync: Install the actual project (Miraiibo/momentum-ops)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 6. Set the path so 'prefect' and other tools work directly
ENV PATH="/app/.venv/bin:$PATH"

# Default command for your Prefect server
CMD ["prefect", "server", "start", "--host", "0.0.0.0"]