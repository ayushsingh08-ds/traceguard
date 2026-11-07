from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.models import RunbookChunk
from app.rca.indexer import DEFAULT_RUNBOOKS, runbook_indexer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed operational runbooks if runbook corpus is empty
    async with AsyncSessionLocal() as session:
        stmt = select(RunbookChunk).limit(1)
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            for rb in DEFAULT_RUNBOOKS:
                await runbook_indexer.index_runbook(
                    session=session,
                    runbook_id=rb["runbook_id"],
                    title=rb["title"],
                    service=rb["service"],
                    markdown_content=rb["content"],
                )

        from datetime import datetime, timedelta, timezone
        from uuid import uuid4
        from app.models import Incident, IncidentStatus, SeverityLevel

        inc_stmt = select(Incident).limit(1)
        inc_res = await session.execute(inc_stmt)
        if not inc_res.scalar_one_or_none():
            now = datetime.now(timezone.utc)
            demo_incidents = [
                Incident(
                    id=uuid4(),
                    fingerprint="1" * 64,
                    title="Database transaction deadlocks on orders table",
                    service="orders-db",
                    environment="production",
                    severity=SeverityLevel.SEV1,
                    status=IncidentStatus.TRIGGERED,
                    occurrence_count=42,
                    first_seen_at=now - timedelta(minutes=6),
                    last_seen_at=now,
                    sla_deadline_at=now + timedelta(minutes=9),
                    raw_payload={"cluster": "aurora-pg-01", "deadlocks_per_sec": 8.4},
                ),
                Incident(
                    id=uuid4(),
                    fingerprint="2" * 64,
                    title="HTTP 504 Gateway Timeouts in payment-api",
                    service="payment-api",
                    environment="production",
                    severity=SeverityLevel.SEV2,
                    status=IncidentStatus.ACKNOWLEDGED,
                    occurrence_count=18,
                    first_seen_at=now - timedelta(minutes=22),
                    last_seen_at=now,
                    sla_deadline_at=now + timedelta(minutes=38),
                    acknowledged_at=now - timedelta(minutes=15),
                    acknowledged_by="lead-engineer",
                    raw_payload={"error_rate_pct": 14.2, "upstream": "stripe-webhook"},
                ),
                Incident(
                    id=uuid4(),
                    fingerprint="3" * 64,
                    title="Kubernetes Pod CrashLoopBackOff in checkout-service",
                    service="checkout-service",
                    environment="production",
                    severity=SeverityLevel.SEV1,
                    status=IncidentStatus.TRIGGERED,
                    occurrence_count=87,
                    first_seen_at=now - timedelta(minutes=3),
                    last_seen_at=now,
                    sla_deadline_at=now + timedelta(minutes=12),
                    raw_payload={"exit_code": 137, "reason": "OOMKilled"},
                ),
                Incident(
                    id=uuid4(),
                    fingerprint="4" * 64,
                    title="High memory usage warning on redis-cache",
                    service="session-cache",
                    environment="production",
                    severity=SeverityLevel.SEV3,
                    status=IncidentStatus.RESOLVED,
                    occurrence_count=5,
                    first_seen_at=now - timedelta(hours=2),
                    last_seen_at=now - timedelta(minutes=30),
                    sla_deadline_at=now + timedelta(hours=2),
                    acknowledged_at=now - timedelta(hours=1, minutes=45),
                    resolved_at=now - timedelta(minutes=30),
                    acknowledged_by="oncall-dev",
                    resolved_by="oncall-dev",
                    raw_payload={"used_memory_pct": 89.2},
                ),
            ]
            session.add_all(demo_incidents)
            await session.commit()

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "healthy", "service": "traceguard-backend"}

