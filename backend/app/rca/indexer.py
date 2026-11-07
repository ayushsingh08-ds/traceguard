import hashlib
import math
import re
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import RunbookChunk
from app.schemas import RunbookSearchResult


def compute_deterministic_embedding(text: str, dimension: int = settings.VECTOR_DIMENSION) -> List[float]:
    # Projects text onto a unit-normalized hypersphere using word and character n-gram hashing.
    # Subword n-grams capture morphological similarity (e.g. 'postgres' and 'postgresql' or 'lock' and 'deadlock')
    # without requiring external network dependencies during offline or test environments.
    words = re.findall(r"\w+", text.lower())
    if not words:
        vector = [0.0] * dimension
        vector[0] = 1.0
        return vector

    tokens: List[str] = list(words)
    for word in words:
        if len(word) >= 3:
            for n in (3, 4):
                for i in range(len(word) - n + 1):
                    tokens.append(word[i : i + n])

    vector = [0.0] * dimension
    for i, token in enumerate(tokens):
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        coord = h % dimension
        sign = 1.0 if ((h >> 8) & 1) else -1.0
        decay = 1.0 / (1.0 + 0.02 * (i % 20))
        vector[coord] += sign * decay

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [round(v / norm, 6) for v in vector]
    else:
        vector[0] = 1.0
    return vector


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


class RunbookIndexer:
    def __init__(self, embedding_dimension: int = settings.VECTOR_DIMENSION) -> None:
        self.embedding_dimension = embedding_dimension

    def chunk_markdown(self, markdown_text: str, max_chunk_chars: int = 800) -> List[str]:
        # Splits runbooks at Markdown heading boundaries (##, ###) to preserve operational context
        sections = re.split(r"\n(?=#{2,4}\s)", markdown_text.strip())
        chunks: List[str] = []

        for section in sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= max_chunk_chars:
                chunks.append(section)
            else:
                paragraphs = section.split("\n\n")
                current = ""
                for p in paragraphs:
                    if len(current) + len(p) + 2 <= max_chunk_chars:
                        current = f"{current}\n\n{p}".strip()
                    else:
                        if current:
                            chunks.append(current)
                        current = p
                if current:
                    chunks.append(current)

        return chunks or [markdown_text.strip()]

    async def index_runbook(
        self,
        session: AsyncSession,
        runbook_id: str,
        title: str,
        service: str,
        markdown_content: str,
    ) -> List[RunbookChunk]:
        chunks = self.chunk_markdown(markdown_content)
        created_chunks: List[RunbookChunk] = []

        for idx, chunk_text in enumerate(chunks):
            embedding = compute_deterministic_embedding(chunk_text, self.embedding_dimension)
            chunk = RunbookChunk(
                id=uuid4(),
                runbook_id=runbook_id,
                title=title,
                service=service.strip().lower(),
                chunk_index=idx,
                content=chunk_text,
                embedding=embedding,
                metadata_json={"char_count": len(chunk_text), "service": service},
            )
            session.add(chunk)
            created_chunks.append(chunk)

        await session.commit()
        return created_chunks

    async def hybrid_search(
        self,
        session: AsyncSession,
        query: str,
        service: Optional[str] = None,
        top_k: int = 3,
    ) -> List[RunbookSearchResult]:
        query_vector = compute_deterministic_embedding(query, self.embedding_dimension)

        stmt = select(RunbookChunk)
        if service:
            stmt = stmt.where(
                (RunbookChunk.service == service.strip().lower())
                | (RunbookChunk.service == "global")
            )

        result = await session.execute(stmt)
        candidates = list(result.scalars().all())

        scored_results: List[RunbookSearchResult] = []
        for chunk in candidates:
            chunk_embedding = chunk.embedding
            # In SQLite or when vector column returns list/string, unpack embedding
            if isinstance(chunk_embedding, (list, tuple)):
                sim = cosine_similarity(query_vector, list(chunk_embedding))
            else:
                sim = 0.5

            scored_results.append(
                RunbookSearchResult(
                    id=chunk.id,
                    runbook_id=chunk.runbook_id,
                    title=chunk.title,
                    service=chunk.service,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    similarity=round(sim, 4),
                )
            )

        scored_results.sort(key=lambda x: x.similarity, reverse=True)
        return scored_results[:top_k]


runbook_indexer = RunbookIndexer()

DEFAULT_RUNBOOKS = [
    {
        "runbook_id": "rbk-postgres-saturation",
        "title": "PostgreSQL Connection Pool & Lock Contention Playbook",
        "service": "orders-db",
        "content": """## Overview
Diagnosing PostgreSQL database pool exhaustion, deadlocks, and slow transactions.

### Diagnostic Steps
1. Execute check_database_locks to check pool saturation and waiting transactions.
2. Query active pg_stat_activity queries where state = 'idle in transaction' or wait_event_type = 'Lock'.
3. Inspect recent deployments to verify whether a schema migration or pool reduction occurred.

### Remediation Protocol
- If pool saturation exceeds 90%, terminate rogue idle transactions using pg_terminate_backend.
- If deadlocks are detected on orders or inventory tables, roll back the recent deployment immediately.
- Temporarily scale PgBouncer connection max_client_conn if server memory allows.""",
    },
    {
        "runbook_id": "rbk-deployment-crashloop",
        "title": "Kubernetes Pod CrashLoopBackOff & OOMKilled Runbook",
        "service": "orders-api",
        "content": """## Overview
Investigating container restart spikes, memory leak threshold violations, and rollout failures.

### Diagnostic Steps
1. Run inspect_recent_deployments to review the latest git commit and image tag.
2. Query telemetry using query_error_rate_spike to check HTTP 504 and 503 error rates.
3. Check pod exit codes: exit code 137 indicates SIGKILL from Linux kernel Out Of Memory (OOM).

### Remediation Protocol
- If exit code is 137, adjust pod memory limit requests in Kubernetes Helm values.
- If errors began precisely at deployment timestamp, execute automated canary rollback via helm rollback.
- Notify release engineer and mark incident acknowledged.""",
    },
    {
        "runbook_id": "rbk-gateway-timeouts",
        "title": "API Gateway 504 Timeout & Downstream Latency Degradation",
        "service": "global",
        "content": """## Overview
Investigating widespread HTTP 504 Gateway Timeouts across edge reverse proxies.

### Diagnostic Steps
1. Execute query_error_rate_spike to verify baseline vs current p99 latency spikes.
2. Check upstream database locks and slow queries.
3. Validate network connectivity and DNS resolution across internal service mesh.

### Remediation Protocol
- Enable rate limiting on aggressive API caller clients.
- Verify whether upstream service circuit breaker has tripped.
- Check downstream database saturation.""",
    },
]
