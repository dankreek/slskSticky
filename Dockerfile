# Multi-stage build for slskSticky
FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md slsksticky.py ./

# Install dependencies and build
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/slsksticky.py /app/slsksticky.py

# Create health directory
RUN mkdir -p /app/health

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Health check using status.json file
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD test -f /app/health/status.json && [ "$(cat /app/health/status.json | python3 -c 'import sys, json; print(json.load(sys.stdin).get(\"healthy\", False))')" = "True" ] || exit 1

# Run the application
CMD ["python", "slsksticky.py"]
