# Owner A — backend/app/tracing.py
#
# OpenTelemetry initialisation stub.
# Owner A wires the exporter and FastAPI/SQLAlchemy auto-instrumentation.
# Owner C fills in the custom business spans (classifier, guardrails, llm, rag).
#
# Traces are exported to Jaeger via OTLP gRPC (port 4317).
# View at http://localhost:16686 during local development.

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(app, engine, otlp_endpoint: str) -> None:
    """
    Initialise OpenTelemetry with OTLP export to Jaeger.
    Call once in lifespan.py after the DB engine is created.

    Auto-instruments:
    - Every FastAPI HTTP request → span with method, path, status code
    - Every SQLAlchemy query → span with SQL statement (no bind params)

    Owner C adds custom spans inside business logic using:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("classifier.call") as span:
            span.set_attribute("tenant_id", str(tenant_id))
    """
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
