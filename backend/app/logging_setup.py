# Owner A — backend/app/logging_setup.py
#
# Configures structlog for structured JSON output.
# Call setup_logging() once at app startup (in lifespan.py).
# Usage anywhere in the codebase:
#
#   import structlog
#   log = structlog.get_logger()
#   log.info("tenant_created", tenant_id=str(tenant_id), slug=slug)
#
# Each call produces one JSON line:
#   {"timestamp": "...", "level": "info", "event": "tenant_created",
#    "tenant_id": "...", "slug": "..."}

import logging
import sys

import structlog


def setup_logging(is_production: bool = False) -> None:
    """
    Configure structlog + standard library logging to output JSON.
    In development: pretty-printed coloured output for readability.
    In production: machine-readable JSON, one object per line.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,        # thread-local context (request_id etc.)
        structlog.stdlib.add_log_level,                 # adds "level" field
        structlog.stdlib.add_logger_name,               # adds "logger" field
        structlog.processors.TimeStamper(fmt="iso"),    # adds "timestamp" in ISO 8601
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_production:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
