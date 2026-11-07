import time
from typing import List
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Incident, IncidentAuditLog, RCAReport
from app.rca.indexer import runbook_indexer
from app.rca.llm_adapter import llm_adapter
from app.rca.tools.registry import diagnostic_tool_registry
from app.schemas import RootCauseReport, RunbookCitation, ToolExecutionRecord


class RCAEngine:
    async def diagnose_incident(
        self,
        session: AsyncSession,
        incident: Incident,
    ) -> RCAReport:
        start_time = time.perf_counter()

        search_query = f"{incident.title} {incident.service} {incident.severity.value}"
        runbook_matches = await runbook_indexer.hybrid_search(
            session=session,
            query=search_query,
            service=incident.service,
            top_k=3,
        )

        citations: List[RunbookCitation] = [
            RunbookCitation(
                runbook_id=m.runbook_id,
                chunk_index=m.chunk_index,
                title=m.title,
                similarity_score=m.similarity,
            )
            for m in runbook_matches
        ]

        # Select deterministic tools based on incident taxonomy and telemetry hints
        tools_to_run: List[str] = ["query_error_rate_spike"]
        text_context = f"{incident.title} {incident.service}".lower()

        if any(w in text_context for w in ("db", "database", "postgres", "sql", "lock", "order", "payment")):
            tools_to_run.append("check_database_locks")
        if any(w in text_context for w in ("deploy", "crash", "release", "pod", "oom", "version", "api")):
            tools_to_run.append("inspect_recent_deployments")

        tools_executed: List[ToolExecutionRecord] = []
        for tool_name in tools_to_run:
            record = await diagnostic_tool_registry.execute(
                name=tool_name,
                service=incident.service,
            )
            tools_executed.append(record)

        incident_context = {
            "id": str(incident.id),
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity.value,
            "environment": incident.environment,
            "occurrence_count": incident.occurrence_count,
        }

        report_schema: RootCauseReport = await llm_adapter.generate_root_cause_report(
            incident_context=incident_context,
            tools_executed=tools_executed,
            retrieved_chunks=citations,
        )

        total_latency_ms = int((time.perf_counter() - start_time) * 1000)

        db_report = RCAReport(
            id=uuid4(),
            incident_id=incident.id,
            hypothesis=report_schema.hypothesis,
            supporting_evidence=report_schema.supporting_evidence,
            confidence_score=report_schema.confidence_score,
            recommended_runbook_steps=report_schema.recommended_runbook_steps,
            tools_executed=[t.model_dump() for t in tools_executed],
            retrieved_chunks=[c.model_dump() for c in citations],
            model_name=report_schema.model_name,
            tokens_used=report_schema.tokens_used,
            execution_time_ms=total_latency_ms,
        )
        session.add(db_report)

        audit_entry = IncidentAuditLog(
            incident_id=incident.id,
            action="RCA_GENERATED",
            actor=report_schema.model_name,
            note=f"RCA generated with confidence {report_schema.confidence_score}",
        )
        session.add(audit_entry)

        await session.commit()
        return db_report


rca_engine = RCAEngine()
