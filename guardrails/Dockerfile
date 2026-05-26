FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/guardrails

RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1.0" \
    "uvicorn[standard]>=0.30,<1.0" \
    "hvac>=2.3,<3.0"

COPY backend /app/backend
COPY guardrails /app/guardrails

EXPOSE 8002

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
