import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Coroutine, List, Optional
import uuid

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models import Incident, IncidentAuditLog, IncidentStatus, SeverityLevel

logger = logging.getLogger("traceguard.workers")


class PriorityIncidentWorker:
    def __init__(
        self,
        worker_id: Optional[str] = None,
        batch_size: int = 5,
        poll_interval_seconds: float = 1.0,
        task_handler: Optional[Callable[[Incident, AsyncSession], Coroutine[None, None, None]]] = None,
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:6]}"
        self.batch_size = batch_size
        self.poll_interval_seconds = poll_interval_seconds
        self.task_handler = task_handler
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def fetch_and_lock_batch(self, session: AsyncSession) -> List[Incident]:
        # Preempt lower-severity incidents using CASE ordering while SKIP LOCKED
        # allows multiple worker processes to poll concurrently without lock convoying.
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
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def process_incident(self, incident: Incident, session: AsyncSession) -> None:
        audit_log = IncidentAuditLog(
            incident_id=incident.id,
            action="DISPATCHED_TO_WORKER",
            actor=self.worker_id,
            previous_status=incident.status.value,
            new_status=incident.status.value,
            note=f"Worker {self.worker_id} acquired lock with severity {incident.severity.value}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit_log)

        if self.task_handler:
            await self.task_handler(incident, session)

    async def run_poll_cycle(self) -> int:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                incidents = await self.fetch_and_lock_batch(session)
                if not incidents:
                    return 0

                for incident in incidents:
                    await self.process_incident(incident, session)

                await session.commit()
                return len(incidents)

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                processed_count = await self.run_poll_cycle()
                if processed_count == 0:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker {self.worker_id} loop: {str(e)}", exc_info=True)
                await asyncio.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

