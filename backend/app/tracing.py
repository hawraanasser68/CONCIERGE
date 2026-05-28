# Owner A / Owner C — backend/app/tracing.py
#
# OpenTelemetry initialisation + safe custom-span helpers.
# Owner A wires the exporter and FastAPI/SQLAlchemy auto-instrumentation.
# Owner C provides safe-attribute helpers for classifier/guardrails/llm/rag spans.
#
# Traces are exported to Jaeger via OTLP gRPC (port 4317) when OpenTelemetry
# dependencies are installed. View at http://localhost:16686 during local development.

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional runtime extras
    trace = None
    OTLPSpanExporter = None
    FastAPIInstrumentor = None
    SQLAlchemyInstrumentor = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    OTEL_AVAILABLE = False


SAFE_ATTRIBUTE_KEYS = {
    "tenant_id",
    "session_id",
    "path",
    "status_code",
    "latency_ms",
    "intent",
    "confidence",
    "allowed",
    "flagged_count",
    "model",
    "tokens_in",
    "tokens_out",
    "hit_count",
    "error_type",
}


def setup_tracing(app, engine, otlp_endpoint: str) -> None:
    """
    Initialise OpenTelemetry with OTLP export to Jaeger.
    Call once in lifespan.py after the DB engine is created.

    Auto-instruments:
    - Every FastAPI HTTP request → span with method, path, status code
    - Every SQLAlchemy query → span with SQL statement (no bind params)

    Owner C custom spans use the safe helpers below so message content and PII
    are never attached to traces.
    """
    if not OTEL_AVAILABLE:
        return

    resource = Resource.create({"service.name": "concierge-backend"})

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Auto-instrument HTTP requests
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument DB queries.
    # Must use engine.sync_engine — SQLAlchemy's async engine blocks direct event
    # listener attachment. The sync_engine unwraps the async layer; all async DB
    # calls still work normally, this only affects where the tracing hooks attach.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def _safe_attrs(attrs: dict[str, Any]) -> dict[str, str | int | float | bool]:
    safe: dict[str, str | int | float | bool] = {}
    for key, value in attrs.items():
        if key not in SAFE_ATTRIBUTE_KEYS or value is None:
            continue
        if isinstance(value, (bool, int, float, str)):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


@contextmanager
def start_span(name: str, **attrs: Any) -> Iterator[Any]:
    """Start a span with safe metadata only; no-op when OpenTelemetry is absent."""
    if not OTEL_AVAILABLE:
        yield None
        return

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        for key, value in _safe_attrs(attrs).items():
            span.set_attribute(key, value)
        yield span


def _record_span(name: str, **attrs: Any) -> None:
    with start_span(name, **attrs):
        return


def record_api_request(
    *,
    tenant_id: Any = None,
    session_id: Any = None,
    path: str,
    latency_ms: float,
    status_code: int | None = None,
) -> None:
    _record_span(
        "api.request",
        tenant_id=tenant_id,
        session_id=session_id,
        path=path,
        latency_ms=latency_ms,
        status_code=status_code,
    )


def record_classifier_call(
    *, tenant_id: Any, intent: str, confidence: float, latency_ms: float
) -> None:
    _record_span(
        "classifier.call",
        tenant_id=tenant_id,
        intent=intent,
        confidence=confidence,
        latency_ms=latency_ms,
    )


def record_guardrails_call(
    *,
    tenant_id: Any,
    session_id: Any = None,
    direction: str,
    allowed: bool,
    flagged_count: int,
    latency_ms: float,
) -> None:
    span_name = "guardrails.input" if direction == "input" else "guardrails.output"
    _record_span(
        span_name,
        tenant_id=tenant_id,
        session_id=session_id,
        allowed=allowed,
        flagged_count=flagged_count,
        latency_ms=latency_ms,
    )


def record_llm_call(
    *,
    tenant_id: Any,
    session_id: Any = None,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
) -> None:
    _record_span(
        "llm.call",
        tenant_id=tenant_id,
        session_id=session_id,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )


def record_rag_retrieve(
    *,
    tenant_id: Any,
    session_id: Any = None,
    hit_count: int,
    latency_ms: float,
) -> None:
    _record_span(
        "rag.retrieve",
        tenant_id=tenant_id,
        session_id=session_id,
        hit_count=hit_count,
        latency_ms=latency_ms,
    )
