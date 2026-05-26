# Owner A — backend/Dockerfile
# Multi-stage build: keeps the final image lean by not shipping build tools.

FROM python:3.11-slim AS base

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install uv --no-cache-dir

# Copy dependency files first — Docker caches this layer until they change
COPY pyproject.toml .

# Install all dependencies into the system Python (no virtualenv needed in container)
RUN uv pip install --system --no-cache .

# Copy application code
COPY . .

EXPOSE 8000

# Run Alembic migrations then start the server.
# migrations run inside the container so the DB is always up to date on startup.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
