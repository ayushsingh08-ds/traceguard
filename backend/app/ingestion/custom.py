from datetime import datetime, timezone
from typing import Any, Dict

from app.ingestion.base import AlertParserStrategy
from app.models import SeverityLevel
from app.schemas import IncidentEvent


class CustomAlertParser(AlertParserStrategy):
    def can_parse(self, payload: Dict[str, Any]) -> bool:
        return True

    def parse(self, payload: Dict[str, Any]) -> IncidentEvent:
        title = (
            payload.get("title")
            or payload.get("alert")
            or payload.get("message")
            or payload.get("error")
            or "Application Alert"
        )
        service = (
            payload.get("service")
            or payload.get("service_name")
            or payload.get("app")
            or "generic-service"
        )
        environment = payload.get("environment") or payload.get("env") or "production"

        raw_severity = str(payload.get("severity") or payload.get("level") or "Sev-2").lower()
        if raw_severity in ("sev-1", "sev1", "critical", "fatal", "p0", "p1"):
            severity = SeverityLevel.SEV1
        elif raw_severity in ("sev-2", "sev2", "warning", "warn", "error", "p2"):
            severity = SeverityLevel.SEV2
        else:
            severity = SeverityLevel.SEV3

        fingerprint = IncidentEvent.compute_fingerprint(service, title, environment)

        return IncidentEvent(
            fingerprint=fingerprint,
            title=str(title)[:255],
            service=str(service)[:100],
            environment=str(environment)[:50],
            severity=severity,
            raw_payload=payload,
            timestamp=datetime.now(timezone.utc),
        )
