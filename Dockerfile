# Astral Market Swarm — Standalone Trading Engine
FROM python:3.11-slim

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy runtime scripts
COPY scripts ./scripts

# Create state directory
RUN mkdir -p /app/state /app/reports /app/logs

# Environment defaults (override at runtime)
ENV DEMO_CASH=5000 \
    DISPLAY_CURRENCY=USDT \
    SYMBOL=BTC/USDT \
    INTERVAL=5m \
    LOOKBACK=250 \
    POLL_SECONDS=300 \
    PORT=8080 \
    STATE_DB=/app/state/orders.sqlite3 \
    BINANCE_PUBLIC_BASE_URL=https://api.binance.com/api/v3 \
    PYTHONUNBUFFERED=1

# Expose HTTP API port
EXPOSE 8080

# Health check (ping /health endpoint)
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the paper trading runtime
CMD ["uv", "run", "python", "-m", "astral_market_swarm.app"]
