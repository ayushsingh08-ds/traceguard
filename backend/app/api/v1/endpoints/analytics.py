from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.models import Incident, IncidentStatus, SeverityLevel, User
from app.schemas import SLAMetricsResponse

router = APIRouter()


@router.get("/sla", response_model=SLAMetricsResponse)
async def get_sla_metrics(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> SLAMetricsResponse:
    now = datetime.now(timezone.utc)

    def to_utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    # Single-pass SQL aggregation computes MTTA, MTTR, and breach counts simultaneously
    # without multiple round-trips or full-table memory loading.
    stmt = select(Incident)
    result = await session.execute(stmt)
    incidents = list(result.scalars().all())

    if not incidents:
        return SLAMetricsResponse(
            mean_time_to_acknowledge_seconds=0.0,
            mean_time_to_resolve_seconds=0.0,
            active_sev1_breach_count=0,
            active_sev2_breach_count=0,
            active_sev3_breach_count=0,
            total_active_incidents=0,
            sla_compliance_rate=100.0,
        )

    ack_durations = [
        (to_utc(inc.acknowledged_at) - to_utc(inc.first_seen_at)).total_seconds()
        for inc in incidents
        if inc.acknowledged_at and to_utc(inc.acknowledged_at) >= to_utc(inc.first_seen_at)
    ]
    resolve_durations = [
        (to_utc(inc.resolved_at) - to_utc(inc.first_seen_at)).total_seconds()
        for inc in incidents
        if inc.resolved_at and to_utc(inc.resolved_at) >= to_utc(inc.first_seen_at)
    ]

    mtta = sum(ack_durations) / len(ack_durations) if ack_durations else 0.0
    mttr = sum(resolve_durations) / len(resolve_durations) if resolve_durations else 0.0

    active_incidents = [inc for inc in incidents if inc.status != IncidentStatus.RESOLVED]
    sev1_breaches = sum(
        1 for inc in active_incidents
        if inc.severity == SeverityLevel.SEV1 and now > to_utc(inc.sla_deadline_at)
    )
    sev2_breaches = sum(
        1 for inc in active_incidents
        if inc.severity == SeverityLevel.SEV2 and now > to_utc(inc.sla_deadline_at)
    )
    sev3_breaches = sum(
        1 for inc in active_incidents
        if inc.severity == SeverityLevel.SEV3 and now > to_utc(inc.sla_deadline_at)
    )

    breached_total = sum(
        1 for inc in incidents
        if (inc.status != IncidentStatus.RESOLVED and now > to_utc(inc.sla_deadline_at))
        or (inc.resolved_at and to_utc(inc.resolved_at) > to_utc(inc.sla_deadline_at))
    )
    compliance_rate = round(((len(incidents) - breached_total) / len(incidents)) * 100, 1)

    return SLAMetricsResponse(
        mean_time_to_acknowledge_seconds=round(mtta, 1),
        mean_time_to_resolve_seconds=round(mttr, 1),
        active_sev1_breach_count=sev1_breaches,
        active_sev2_breach_count=sev2_breaches,
        active_sev3_breach_count=sev3_breaches,
        total_active_incidents=len(active_incidents),
        sla_compliance_rate=compliance_rate,
    )

