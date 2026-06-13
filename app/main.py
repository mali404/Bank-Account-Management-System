"""FastAPI application factory with OpenTelemetry, Prometheus, rate limiting."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api import accounts_router, agent_router, auth_router, transfers_router
from app.core.settings import get_settings
from app.openbanking import (
    router_aisp,
    router_oauth,
    router_opendata,
    router_pisp,
)


def _configure_logging() -> None:
    logging.basicConfig(level=get_settings().log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


def _configure_otel(app: FastAPI) -> None:
    s = get_settings()
    resource = Resource.create({"service.name": s.otel_service_name, "deployment.environment": s.app_env})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_exporter_otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Agentic Bank",
        version="0.1.0",
        description="Hybrid multi-agent banking system with NIST-aligned security.",
        lifespan=lifespan,
    )
    # Rate limiting (NIST SC-5): the Limiter alone is inert — the
    # middleware applies default limits and the handler shapes 429s.
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[s.rate_limit_default],
        storage_uri=s.redis_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(auth_router.router)
    app.include_router(accounts_router.router)
    app.include_router(transfers_router.router)
    app.include_router(agent_router.router)

    # Open Banking (OBIE-aligned) — see docs/openbanking/README.md
    app.include_router(router_opendata.router)
    app.include_router(router_oauth.router)
    app.include_router(router_aisp.router)
    app.include_router(router_pisp.router)

    if s.prometheus_enabled:
        Instrumentator().instrument(app).expose(app)

    _configure_otel(app)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
