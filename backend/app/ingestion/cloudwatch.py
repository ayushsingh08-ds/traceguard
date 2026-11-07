import json
from datetime import datetime, timezone
from typing import Any, Dict

from app.ingestion.base import AlertParserStrategy
from app.models import SeverityLevel
from app.schemas import IncidentEvent


class CloudWatchAlertParser(AlertParserStrategy):
    def can_parse(self, payload: Dict[str, Any]) -> bool:
        if "AlarmName" in payload or "NewStateValue" in payload:
            return True
        if payload.get("Type") == "Notification" and "TopicArn" in payload and "Message" in payload:
            return True
        return False

    def parse(self, payload: Dict[str, Any]) -> IncidentEvent:
        parsed_payload = payload
        # AWS SNS encapsulates notifications within a serialized JSON string in the 'Message' key
        if payload.get("Type") == "Notification" and isinstance(payload.get("Message"), str):
            try:
                parsed_payload = json.loads(payload["Message"])
            except json.JSONDecodeError:
                parsed_payload = payload

        title = parsed_payload.get("AlarmName") or parsed_payload.get("Subject") or "CloudWatch Alarm"
        trigger = parsed_payload.get("Trigger", {})
        dimensions = trigger.get("Dimensions", [])

        service = "aws-cloudwatch"
        if dimensions and isinstance(dimensions, list):
            for dim in dimensions:
                if isinstance(dim, dict) and "value" in dim:
                    service = dim["value"]
                    break
        elif "Namespace" in trigger:
            service = trigger["Namespace"]

        environment = "production"
        if "staging" in title.lower() or "dev" in title.lower():
            environment = "staging"

        text_to_scan = f"{title} {parsed_payload.get('AlarmDescription', '')}".lower()
        if any(term in text_to_scan for term in ("sev-1", "sev1", "critical", "p0", "p1")):
            severity = SeverityLevel.SEV1
        elif any(term in text_to_scan for term in ("sev-2", "sev2", "warning", "high", "p2")):
            severity = SeverityLevel.SEV2
        else:
            severity = SeverityLevel.SEV3

        fingerprint = IncidentEvent.compute_fingerprint(service, title, environment)

        timestamp = datetime.now(timezone.utc)
        state_change_time = parsed_payload.get("StateChangeTime")
        if state_change_time:
            try:
                cleaned = state_change_time.replace("+0000", "+00:00")
                timestamp = datetime.fromisoformat(cleaned)
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

