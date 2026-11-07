import math
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from app.models import Incident, IncidentStatus, SeverityLevel
from app.rca.engine import RCAEngine
from app.rca.indexer import RunbookIndexer, compute_deterministic_embedding, cosine_similarity
from app.rca.llm_adapter import LLMAdapter
from app.rca.tools.registry import DiagnosticToolRegistry
from app.schemas import RootCauseReport, RunbookCitation, ToolExecutionRecord


def test_deterministic_embedding_properties():
    text1 = "PostgreSQL deadlock detected on customer orders table"
    text2 = "Postgres database lock contention and connection pool exhaustion"
    text3 = "Kubernetes frontend pod nginx image pull backoff"

    v1 = compute_deterministic_embedding(text1, dimension=768)
    v2 = compute_deterministic_embedding(text2, dimension=768)
    v3 = compute_deterministic_embedding(text3, dimension=768)

    assert len(v1) == 768
    norm1 = math.sqrt(sum(x * x for x in v1))
    assert math.isclose(norm1, 1.0, rel_tol=1e-3)

    sim_self = cosine_similarity(v1, v1)
    assert math.isclose(sim_self, 1.0, rel_tol=1e-3)

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > sim_unrelated


def test_markdown_runbook_chunker():
    indexer = RunbookIndexer()
    md = """## Overview
Database troubleshooting procedures for high connection spikes.

### Investigation
Check active locks and query pg_stat_activity.

### Remediation
Terminate blocking pids using pg_terminate_backend."""

    chunks = indexer.chunk_markdown(md, max_chunk_chars=120)
    assert len(chunks) >= 2
    assert any("Overview" in c for c in chunks)
    assert any("Remediation" in c for c in chunks)


@pytest.mark.asyncio
async def test_diagnostic_tool_registry():
    registry = DiagnosticToolRegistry()
    specs = registry.get_openai_tools_spec()
    assert len(specs) >= 3
    names = [s["function"]["name"] for s in specs]
    assert "check_database_locks" in names
    assert "inspect_recent_deployments" in names
    assert "query_error_rate_spike" in names

    record = await registry.execute("check_database_locks", service="orders-db")
    assert record.tool_name == "check_database_locks"
    assert record.result["has_deadlock"] is True
    assert record.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_llm_adapter_deterministic_fallback():
    adapter = LLMAdapter(api_key=None)

    tools = [
        ToolExecutionRecord(
            tool_name="check_database_locks",
            parameters={"service": "orders-db"},
            result={"pool_saturation_pct": 94.0, "has_deadlock": True, "active_connections": 94, "max_connections": 100, "blocked_transactions_count": 14},
            execution_time_ms=12,
        ),
        ToolExecutionRecord(
            tool_name="query_error_rate_spike",
            parameters={"service": "orders-db"},
            result={"current_http_5xx_rate_pct": 18.2, "baseline_http_5xx_rate_pct": 0.05, "p99_latency_ms": 6800},
            execution_time_ms=8,
        ),
    ]

    citations = [
        RunbookCitation(
            runbook_id="rbk-postgres-saturation",
            chunk_index=0,
            title="PostgreSQL Connection Pool & Lock Contention Playbook",
            similarity_score=0.91,
        )
    ]

    report = await adapter.generate_root_cause_report(
        incident_context={"service": "orders-db", "title": "Deadlock burst", "severity": "Sev-1"},
        tools_executed=tools,
        retrieved_chunks=citations,
    )

    assert isinstance(report, RootCauseReport)
    assert 0.0 <= report.confidence_score <= 1.0
    assert len(report.supporting_evidence) >= 2
    assert len(report.recommended_runbook_steps) >= 1
    assert "database" in report.hypothesis.lower()


@pytest.mark.asyncio
async def test_rca_engine_orchestration():
    engine = RCAEngine()

    mock_incident = Incident(
        id=uuid4(),
        fingerprint="c" * 64,
        title="High Database Lock Contention",
        service="orders-db",
        environment="production",
        severity=SeverityLevel.SEV1,
        status=IncidentStatus.TRIGGERED,
        occurrence_count=42,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    db_report = await engine.diagnose_incident(session=mock_session, incident=mock_incident)

    assert db_report.incident_id == mock_incident.id
    assert db_report.confidence_score >= 0.8
    assert len(db_report.tools_executed) >= 2
    assert mock_session.add.call_count >= 2
    mock_session.commit.assert_awaited_once()
