FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/modelserver

RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1.0" \
    "uvicorn[standard]>=0.30,<1.0" \
    "scikit-learn>=1.5,<2.0" \
    "joblib>=1.4,<2.0" \
    "numpy>=1.26,<3.0" \
    "onnxruntime>=1.18,<2.0" \
    "pyyaml>=6.0,<7.0" \
    "hvac>=2.3,<3.0" \
    "openai>=1.0,<2.0"

COPY . /app/modelserver

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
