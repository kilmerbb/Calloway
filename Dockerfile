# ── Stage 1: Build dependencies ────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r calloway && useradd -r -g calloway -s /usr/sbin/nologin calloway

# Unbuffered output + no .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=calloway:calloway . .

# Ensure entrypoint is executable
RUN chmod +x docker-entrypoint.sh

# Switch to non-root user
USER calloway

# PROCESS_TYPE controls which process starts: "web" (default) or "worker"
ENV PROCESS_TYPE=web \
    PORT=8000
EXPOSE ${PORT}

# Health check: web uses /health endpoint, worker uses sentinel file.
# The web healthcheck is the default; docker-compose overrides for worker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
