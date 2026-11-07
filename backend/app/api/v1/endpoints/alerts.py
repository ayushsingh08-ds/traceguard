from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4
from fastapi import APIRouter, Depends, status
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_redis_dep
from app.ingestion.deduplicator import AlertDeduplicator
from app.ingestion.parser_factory import alert_parser_registry
from app.models import Incident, IncidentAuditLog, IncidentStatus
from app.schemas import IncidentEvent

router = APIRouter()


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def ingest_alert_webhook(
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_dep),
) -> Dict[str, Any]:
    event: IncidentEvent = alert_parser_registry.resolve_and_parse(payload)
    deduplicator = AlertDeduplicator(redis_client=redis_client)
    dedup_res = await deduplicator.evaluate_and_record(event.fingerprint)

    stmt = (
        select(Incident)
        .where(Incident.fingerprint == event.fingerprint)
        .where(Incident.status != IncidentStatus.RESOLVED)
    )
    result = await session.execute(stmt)
    existing_incident = result.scalar_one_or_none()

    if existing_incident:
        existing_incident.occurrence_count = dedup_res.occurrence_count
        existing_incident.last_seen_at = datetime.now(timezone.utc)

        audit_entry = IncidentAuditLog(
            incident_id=existing_incident.id,
            action="DEDUPLICATED",
            actor="deduplicator",
            note=f"Suppressed duplicate alert burst (count: {dedup_res.occurrence_count})",
        )
        session.add(audit_entry)
        await session.commit()

        return {
            "status": "deduplicated",
            "incident_id": str(existing_incident.id),
            "fingerprint": event.fingerprint,
            "occurrence_count": existing_incident.occurrence_count,
            "is_duplicate": True,
        }

    sla_deadline = IncidentEvent.calculate_sla_deadline(event.severity, event.timestamp)
    new_id = uuid4()
    new_incident = Incident(
        id=new_id,
        fingerprint=event.fingerprint,
        title=event.title,
        service=event.service,
        environment=event.environment,
        severity=event.severity,
        status=IncidentStatus.TRIGGERED,
        occurrence_count=1,
        first_seen_at=event.timestamp,
        last_seen_at=event.timestamp,
        sla_deadline_at=sla_deadline,
        raw_payload=payload,
    )
    session.add(new_incident)

    audit_entry = IncidentAuditLog(
        id=uuid4(),
        incident_id=new_id,
        action="TRIGGERED",
        actor="ingestion-perimeter",
        new_status=IncidentStatus.TRIGGERED.value,
        note=f"Incident opened with SLA deadline {sla_deadline.isoformat()}",
    )
    session.add(audit_entry)
    await session.commit()

    return {
        "status": "created",
        "incident_id": str(new_incident.id),
        "fingerprint": event.fingerprint,
        "occurrence_count": 1,
        "is_duplicate": False,
    }
