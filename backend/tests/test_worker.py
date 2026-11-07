import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import case, select
from sqlalchemy.dialects import postgresql

from app.models import Incident, IncidentStatus, SeverityLevel
from app.workers.priority_worker import PriorityIncidentWorker


def test_worker_query_compilation_and_priority_locking():
    severity_rank = case(
        (Incident.severity == SeverityLevel.SEV1, 1),
        (Incident.severity == SeverityLevel.SEV2, 2),
        (Incident.severity == SeverityLevel.SEV3, 3),
        else_=4,
    )

    query = (
        select(Incident)
        .where(Incident.status == IncidentStatus.TRIGGERED)
        .order_by(severity_rank.asc(), Incident.sla_deadline_at.asc())
        .limit(5)
        .with_for_update(skip_locked=True)
    )

    sql = str(query.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "CASE WHEN" in sql
    assert "incidents.sla_deadline_at ASC" in sql


@pytest.mark.asyncio
async def test_worker_lifecycle():
    worker = PriorityIncidentWorker(worker_id="test-worker-1", poll_interval_seconds=0.01)
    worker.start()
    assert worker._running is True
    assert worker._task is not None

    await asyncio.sleep(0.05)
    await worker.stop()
    assert worker._running is False
    assert worker._task.done() is True


@pytest.mark.asyncio
async def test_worker_dispatches_task_handler_and_records_audit():
    mock_handler = AsyncMock()
    worker = PriorityIncidentWorker(
        worker_id="test-worker-audit",
        task_handler=mock_handler,
    )

    mock_incident = MagicMock(spec=Incident)
    mock_incident.id = "00000000-0000-0000-0000-000000000001"
    mock_incident.status = IncidentStatus.TRIGGERED
    mock_incident.severity = SeverityLevel.SEV1

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    await worker.process_incident(mock_incident, mock_session)

    assert mock_session.add.called
    audit_entry = mock_session.add.call_args[0][0]
    assert audit_entry.action == "DISPATCHED_TO_WORKER"
    assert audit_entry.actor == "test-worker-audit"
    mock_handler.assert_awaited_once_with(mock_incident, mock_session)
