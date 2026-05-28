FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/modelserver

# Deployed model is classical (sklearn + joblib). No onnxruntime: the DL ONNX
# baseline is a documented comparison only and is never served at runtime.
# binutils is installed only to strip native debug symbols, then purged in the
# same layer so it leaves no footprint in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils \
    && pip install --no-cache-dir \
        "fastapi>=0.115,<1.0" \
        "uvicorn[standard]>=0.30,<1.0" \
        "scikit-learn>=1.5,<2.0" \
        "joblib>=1.4,<2.0" \
        "numpy>=1.26,<3.0" \
        "pyyaml>=6.0,<7.0" \
        "hvac>=2.3,<3.0" \
        "openai>=1.0,<2.0" \
    # Strip build-time-only bulk that is never needed at serve time
    && find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -type d -name tests -prune -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -type d -name test -prune -exec rm -rf {} + \
    # Strip native debug symbols from scientific libs (scipy/numpy/sklearn shared objects)
    && find /usr/local/lib/python3.11/site-packages -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true \
    # pip + setuptools are not needed once dependencies are installed
    && rm -rf /usr/local/lib/python3.11/site-packages/pip \
              /usr/local/lib/python3.11/site-packages/setuptools \
              /usr/local/lib/python3.11/site-packages/pkg_resources \
    # Purge binutils and apt lists so they leave no footprint
    && apt-get purge -y binutils \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/modelserver

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
