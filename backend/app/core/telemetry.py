"""Optional OpenTelemetry tracing for the FastAPI application."""

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(app: FastAPI) -> None:
    """Enable tracing only when explicitly configured."""
    if os.getenv("DT_TRACING_ENABLED", "false").lower() != "true":
        return

    endpoint = os.getenv("DT_OTLP_TRACES_ENDPOINT")
    token = os.getenv("DT_API_TOKEN")

    if not endpoint or not token:
        raise RuntimeError(
            "Dynatrace tracing requires DT_OTLP_TRACES_ENDPOINT and DT_API_TOKEN"
        )

    if not endpoint.startswith("https://"):
        raise ValueError("Dynatrace OTLP endpoint must use HTTPS")

    attributes = {"service.name": "secure-backend-platform"}
    if environment := os.getenv("DT_ENVIRONMENT"):
        attributes["deployment.environment.name"] = environment
    if run_id := os.getenv("DT_RUN_ID"):
        attributes["ci.github.run_id"] = run_id

    resource = Resource.create(attributes)
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
    )
