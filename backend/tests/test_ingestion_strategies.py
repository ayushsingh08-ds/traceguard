from app.ingestion.cloudwatch import CloudWatchAlertParser
from app.ingestion.custom import CustomAlertParser
from app.ingestion.parser_factory import alert_parser_registry
from app.ingestion.prometheus import PrometheusAlertParser
from app.models import SeverityLevel


def test_prometheus_alert_parser_maps_critical_to_sev1():
    parser = PrometheusAlertParser()
    payload = {
        "receiver": "webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "DatabaseDeadlockDetected",
                    "service": "orders-db",
                    "severity": "critical",
                    "environment": "production",
                },
                "annotations": {
                    "summary": "Postgres transactions encountering deadlocks > 5/sec",
                },
                "startsAt": "2026-11-07T10:00:00Z",
            }
        ],
    }

    assert parser.can_parse(payload) is True
    event = parser.parse(payload)
    assert event.service == "orders-db"
    assert event.title == "DatabaseDeadlockDetected"
    assert event.severity == SeverityLevel.SEV1
    assert event.environment == "production"
    assert len(event.fingerprint) == 64


def test_cloudwatch_alert_parser_sns_envelope():
    parser = CloudWatchAlertParser()
    sns_payload = {
        "Type": "Notification",
        "MessageId": "95df01b4-ee98-5cb9-9903-4c221d41eb5e",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:cloudwatch-alarms",
        "Subject": "ALARM: HighCPUUtilization in us-east-1",
        "Message": (
            '{"AlarmName":"HighCPUUtilization-orders-api","AlarmDescription":"Sev-1 CPU spike > 95%",'
            '"NewStateValue":"ALARM","Trigger":{"Namespace":"AWS/ECS","Dimensions":[{"name":"ClusterName","value":"orders-api"}]}}'
        ),
    }

    assert parser.can_parse(sns_payload) is True
    event = parser.parse(sns_payload)
    assert event.service == "orders-api"
    assert event.title == "HighCPUUtilization-orders-api"
    assert event.severity == SeverityLevel.SEV1
    assert len(event.fingerprint) == 64


def test_custom_parser_and_registry_resolution():
    payload = {
        "service": "billing-service",
        "title": "Payment gateway timeout rate > 5%",
        "severity": "Sev-2",
        "environment": "staging",
    }

    event = alert_parser_registry.resolve_and_parse(payload)
    assert event.service == "billing-service"
    assert event.title == "Payment gateway timeout rate > 5%"
    assert event.severity == SeverityLevel.SEV2
    assert event.environment == "staging"
