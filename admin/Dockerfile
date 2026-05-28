# Owner D — admin Streamlit container.
# Lean python:3.12-slim base. Installs uv for fast deps install. No build step
# (Streamlit serves Python directly), so this is a single-stage image.

FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY app.py ./
COPY lib ./lib
COPY pages ./pages

EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health').read()" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
