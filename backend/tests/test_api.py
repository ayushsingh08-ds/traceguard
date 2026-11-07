from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db_session, get_redis_dep
from app.core.database import Base
from app.main import app
from app.models import Incident, IncidentStatus, SeverityLevel

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


class MockRedis:
    def __init__(self):
        self._counts = {}

    def pipeline(self, transaction=True):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def zremrangebyscore(self, *args, **kwargs):
        pass

    def zcard(self, key):
        pass

    def zadd(self, *args, **kwargs):
        pass

    def expire(self, *args, **kwargs):
        pass

    async def execute(self):
        return [0, 0, 1, True]


async def override_get_redis():
    return None


app.dependency_overrides[get_db_session] = override_get_db
app.dependency_overrides[get_redis_dep] = override_get_redis


@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_auth_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "staff-engineer", "password": "securepassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_alert_webhook_ingestion_and_deduplication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "service": "checkout-api",
            "title": "Payment gateway timeout rate > 5%",
            "severity": "Sev-1",
            "environment": "production",
        }

        resp1 = await client.post("/api/v1/alerts/webhook", json=payload)
        assert resp1.status_code == 202
        body1 = resp1.json()
        assert body1["status"] == "created"
        assert body1["is_duplicate"] is False
        assert body1["occurrence_count"] == 1

        resp2 = await client.post("/api/v1/alerts/webhook", json=payload)
        assert resp2.status_code == 202
        body2 = resp2.json()
        assert body2["status"] == "deduplicated"
        assert body2["is_duplicate"] is True
        assert body2["occurrence_count"] == 2


@pytest.mark.asyncio
async def test_incident_status_transition():
    now = datetime.now(timezone.utc)
    incident_id = uuid4()

    async with TestSessionLocal() as session:
        inc = Incident(
            id=incident_id,
            fingerprint="d" * 64,
            title="Redis OOM Outage",
            service="session-cache",
            environment="production",
            severity=SeverityLevel.SEV1,
            status=IncidentStatus.TRIGGERED,
            first_seen_at=now,
            last_seen_at=now,
            sla_deadline_at=now + timedelta(minutes=15),
        )
        session.add(inc)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patch_resp = await client.patch(
            f"/api/v1/incidents/{incident_id}/status",
            json={"status": "ACKNOWLEDGED", "actor": "ayush-staff-eng"},
        )
        assert patch_resp.status_code == 200
        patch_data = patch_resp.json()
        assert patch_data["status"] == "ACKNOWLEDGED"
        assert patch_data["acknowledged_by"] == "ayush-staff-eng"
        assert patch_data["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_sla_analytics_calculation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/analytics/sla")
        assert resp.status_code == 200
        data = resp.json()
        assert "mean_time_to_acknowledge_seconds" in data
        assert "mean_time_to_resolve_seconds" in data
        assert "sla_compliance_rate" in data
        assert "total_active_incidents" in data
