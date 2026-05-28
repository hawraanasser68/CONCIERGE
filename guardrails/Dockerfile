# Owner C — multi-stage guardrails image; target < 600 MB, no torch/transformers
# syntax=docker/dockerfile:1.4

# Stage 1: build native wheels
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

COPY requirements.txt .

RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: lean runtime image
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/guardrails

# Install wheels via bind-mount — no persistent /wheels layer left in the image
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels \
        fastapi \
        "uvicorn[standard]" \
        hvac \
        presidio-analyzer \
        presidio-anonymizer \
        spacy \
        httpx

# Pre-bake small spaCy model before stripping — spacy.training is needed for the download
RUN python -m spacy download en_core_web_sm

# Strip spaCy internals not needed at runtime (tokenizer + NER is all we use)
RUN find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -type d -name tests -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -type d -name test -exec rm -rf {} + \
    && rm -rf /usr/local/lib/python3.11/site-packages/spacy/pipeline/_parser_internals \
    && rm -rf /usr/local/lib/python3.11/site-packages/spacy/training \
    && rm -rf /usr/local/lib/python3.11/site-packages/spacy/kb \
    && rm -rf /usr/local/lib/python3.11/site-packages/spacy/displacy \
    && rm -rf /usr/local/lib/python3.11/site-packages/spacy/cli \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip /usr/local/lib/python3.11/site-packages/setuptools

# Pre-fetch tldextract Public Suffix List so first request isn't slow and offline
RUN python -c "import tldextract; tldextract.TLDExtract(cache_dir='/app/tldextract_cache').update()"

ENV TLDEXTRACT_CACHE_DIR=/app/tldextract_cache

COPY . /app/guardrails

EXPOSE 8002

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
