from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.models import Incident, RCAReport, User
from app.rca.engine import rca_engine
from app.schemas import RCAReportResponse

router = APIRouter()


@router.post("/{incident_id}/diagnose", response_model=RCAReportResponse)
async def trigger_rca_diagnosis(
    incident_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> RCAReport:
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await session.execute(stmt)
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )

    report = await rca_engine.diagnose_incident(session=session, incident=incident)
    return report


@router.get("/{incident_id}/report", response_model=RCAReportResponse)
async def get_latest_rca_report(
    incident_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> RCAReport:
    stmt = (
        select(RCAReport)
        .where(RCAReport.incident_id == incident_id)
        .order_by(RCAReport.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No RCA report generated for incident '{incident_id}'",
        )
    return report

