from typing import Any, Dict
from app.rca.tools.base import DiagnosticTool


class QueryErrorRateSpikeTool(DiagnosticTool):
    @property
    def name(self) -> str:
        return "query_error_rate_spike"

    @property
    def description(self) -> str:
        return "Queries telemetry metrics for HTTP 5xx error spikes, p99 latency degradation, and dependency failures."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The microservice to query metrics for.",
                },
                "window_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes to analyze.",
                    "default": 15,
                },
            },
            "required": ["service"],
        }

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        service = kwargs.get("service", "unknown")

        return {
            "service": service,
            "baseline_http_5xx_rate_pct": 0.05,
            "current_http_5xx_rate_pct": 14.8,
            "p95_latency_ms": 3200,
            "p99_latency_ms": 7800,
            "baseline_p99_latency_ms": 180,
            "top_error_signatures": [
                "HTTP 504 Gateway Timeout: Upstream DB query timeout exceeded 5000ms",
                "HTTP 503 Service Unavailable: Connection pool exhausted, queue capacity full",
            ],
            "degraded_upstream_dependencies": ["orders-db-primary", "auth-session-redis"],
        }

