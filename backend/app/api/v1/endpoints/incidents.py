from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db_session
from app.models import Incident, IncidentAuditLog, IncidentStatus, SeverityLevel, User
from app.schemas import (
    IncidentDetailResponse,
    IncidentListItem,
    IncidentUpdateStatus,
)

router = APIRouter()


@router.get("", response_model=List[IncidentListItem])
async def list_incidents(
    status_filter: Optional[IncidentStatus] = Query(None, alias="status"),
    severity_filter: Optional[SeverityLevel] = Query(None, alias="severity"),
    service_filter: Optional[str] = Query(None, alias="service"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> List[Incident]:
    stmt = select(Incident)

    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    if severity_filter:
        stmt = stmt.where(Incident.severity == severity_filter)
    if service_filter:
        stmt = stmt.where(Incident.service == service_filter.strip().lower())

    stmt = stmt.order_by(Incident.sla_deadline_at.asc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> Incident:
    # selectinload eagerly resolves 1:N relations in two queries, eliminating async N+1 lazy-load errors
    stmt = (
        select(Incident)
        .options(
            selectinload(Incident.audit_logs),
            selectinload(Incident.rca_reports),
        )
        .where(Incident.id == incident_id)
    )
    result = await session.execute(stmt)
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    return incident


@router.patch("/{incident_id}/status", response_model=IncidentListItem)
async def update_incident_status(
    incident_id: UUID,
    payload: IncidentUpdateStatus,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Incident:
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await session.execute(stmt)
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    previous_status = incident.status
    now = datetime.now(timezone.utc)
    actor = payload.actor or current_user.username

    incident.status = payload.status

    if payload.status == IncidentStatus.ACKNOWLEDGED and not incident.acknowledged_at:
        incident.acknowledged_at = now
        incident.acknowledged_by = actor
    elif payload.status == IncidentStatus.RESOLVED:
        incident.resolved_at = now
        incident.resolved_by = actor

    audit_entry = IncidentAuditLog(
        incident_id=incident.id,
        action=f"STATUS_TRANSITION_TO_{payload.status.value}",
        actor=actor,
        previous_status=previous_status.value,
        new_status=payload.status.value,
        note=payload.note or f"Status shifted from {previous_status.value} to {payload.status.value}",
    )
    session.add(audit_entry)
    await session.commit()
    await session.refresh(incident)

    return incident

