"""In-process OpenTelemetry spans for one agent run (SPEC §5.4, §12 AU-3).

The SDK exporter is in memory. Jaeger and OpenSearch are the compose
overlay in ``deploy/compose.obs.yaml``; unit tests do not start them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span

__all__ = ["finished_spans", "reset_spans", "span"]

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)
_tracer = trace.get_tracer("agentbank")


@contextmanager
def span(name: str, attributes: dict[str, str]) -> Iterator[Span]:
    """Start a span and set string attributes. The span ends when the block does."""
    with _tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            current.set_attribute(key, value)
        yield current


def finished_spans() -> list[object]:
    """Spans the in-memory exporter has finished."""
    return list(_exporter.get_finished_spans())


def reset_spans() -> None:
    """Drop finished spans. Used by tests so runs do not leak into each other."""
    _exporter.clear()
