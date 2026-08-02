"""OpenTelemetry tracing for the MCP servers (cloud-only).

Gives each FastMCP server first-class spans in Cloud Trace, joined to the
calling agent's trace (trace context is extracted from incoming headers — both
W3C `traceparent` and Google's `X-Cloud-Trace-Context`). This is what makes the
MCP servers appear as their own nodes in Monitoring's Application Topology
instead of only being discovered from agent-side client spans.

No-ops entirely when running locally (RUN_LOCAL auto-detect) or when the OTel
packages aren't installed — the local compose mesh stays untouched.
"""


def setup_otel(service_name: str) -> bool:
    from vibeflix_common.platform.cloud_auth import run_local
    if run_local():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
        from opentelemetry.instrumentation.starlette import StarletteInstrumentor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)
        set_global_textmap(CompositePropagator(
            [TraceContextTextMapPropagator(), CloudTraceFormatPropagator()]))
        StarletteInstrumentor().instrument()  # patches the app FastMCP builds internally
        print(f"[otel] tracing on → Cloud Trace as service.name={service_name}", flush=True)
        return True
    except Exception as e:  # missing packages / no ADC — never block serving
        print(f"[otel] disabled ({type(e).__name__}: {e})", flush=True)
        return False
