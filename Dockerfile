# Use the official uv image for the build stage
FROM python3.13-bookworm-slim AS builder

# 1. Setup working directory
WORKDIR /app

# 2. Optimization: Enable bytecode compilation and use 'copy' mode
# (Hardlinks don't work across Docker layers)
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# 3. Cache dependencies: Copy only the lockfile and project metadata first
# This layer is ONLY rebuilt if your dependencies change.
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev

# 4. Copy the rest of your Miraiibo source code
ADD . /app

# 5. Final sync: Install the actual project (Miraiibo/momentum-ops)
RUN uv sync --frozen --no-dev

# 6. Set the path so 'prefect' and other tools work directly
ENV PATH="/app/.venv/bin:$PATH"

# Default command for your Prefect server
CMD ["prefect", "server", "start", "--host", "0.0.0.0"]