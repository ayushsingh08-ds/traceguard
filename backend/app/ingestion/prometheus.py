from datetime import datetime, timezone
from typing import Any, Dict

from app.ingestion.base import AlertParserStrategy
from app.models import SeverityLevel
from app.schemas import IncidentEvent


class PrometheusAlertParser(AlertParserStrategy):
    def can_parse(self, payload: Dict[str, Any]) -> bool:
        return "receiver" in payload or "alerts" in payload or "groupLabels" in payload

    def parse(self, payload: Dict[str, Any]) -> IncidentEvent:
        alerts = payload.get("alerts", [])
        alert_data = alerts[0] if alerts else payload

        labels = alert_data.get("labels", {})
        annotations = alert_data.get("annotations", {})

        title = (
            labels.get("alertname")
            or annotations.get("summary")
            or annotations.get("description")
            or "Prometheus Alert"
        )
        service = (
            labels.get("service")
            or labels.get("job")
            or labels.get("app")
            or "unknown-service"
        )
        environment = labels.get("environment", "production")

        raw_severity = str(labels.get("severity", "warning")).lower()
        if raw_severity in ("critical", "page", "fatal", "sev1", "sev-1"):
            severity = SeverityLevel.SEV1
        elif raw_severity in ("warning", "error", "sev2", "sev-2"):
            severity = SeverityLevel.SEV2
        else:
            severity = SeverityLevel.SEV3

        fingerprint = IncidentEvent.compute_fingerprint(service, title, environment)

        starts_at_raw = alert_data.get("startsAt")
        timestamp = datetime.now(timezone.utc)
        if starts_at_raw:
            try:
                timestamp = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        return IncidentEvent(
            fingerprint=fingerprint,
            title=title,
            service=service,
            environment=environment,
            severity=severity,
            raw_payload=payload,
            timestamp=timestamp,
        )

