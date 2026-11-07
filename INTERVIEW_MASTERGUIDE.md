# TraceGuard: Technical Architecture & Interview Master Guide

## System Architecture Diagram

```
+----------------------------------------------------------------------------------------------------+
|                                      EXTERNAL ALERT SOURCES                                        |
|   +-----------------------+     +------------------------+     +-------------------------------+   |
|   | Prometheus Alertmgr   |     | AWS CloudWatch Alarm   |     | Custom App Microservice Log   |   |
|   +-----------+-----------+     +-----------+------------+     +---------------+---------------+   |
+---------------|-----------------------------|----------------------------------|-------------------+
                | (Webhook POST)              | (Webhook POST)                   | (Webhook POST)
                +----------------------+      |      +---------------------------+
                                       |      |      |
                                       v      v      v
+----------------------------------------------------------------------------------------------------+
|                                    TRACEGUARD INGESTION LAYER                                      |
|                                                                                                    |
|   +--------------------------------------------------------------------------------------------+   |
|   | Parser Strategy Pattern: Normalizes heterogeneous JSON into immutable IncidentEvent domain |   |
|   | SHA-256 Payload Fingerprinting: sha256(lowercase(service:title:environment))              |   |
|   +----------------------------------------------+---------------------------------------------+   |
|                                                  |                                                 |
|                                                  v                                                 |
|   +--------------------------------------------------------------------------------------------+   |
|   | Redis Sliding-Window Deduplicator (ZSET): Drops duplicate bursts, atom. increments counter |   |
|   +----------------------------------------------+---------------------------------------------+   |
+--------------------------------------------------|-------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                  PERSISTENCE LAYER (PostgreSQL 16)                                 |
|                                                                                                    |
|   +--------------------------------------------------------------------------------------------+   |
|   | Relational Store: incidents, incident_audit_logs, users                                    |   |
|   | Composite Index: (status, severity, sla_deadline_at) for fast SLA breach & queue scans    |   |
|   +----------------------------------------------+---------------------------------------------+   |
|   | Vector Store (pgvector): runbook_chunks                                                    |   |
|   | HNSW Index (m=16, ef_construction=64, vector_cosine_ops) for semantic runbook retrieval  |   |
|   +----------------------------------------------+---------------------------------------------+   |
+--------------------------------------------------|-------------------------------------------------+
                                                   |
                     +-----------------------------+-----------------------------+
                     |                                                           |
                     v                                                           v
+----------------------------------------------------+  +--------------------------------------------+
|         CONCURRENT PRIORITY WORKER POOL            |  |             FASTAPI REST API               |
|                                                    |  |                                            |
| - asyncio worker coroutines                        |  | - JWT Bearer Authentication (RBAC)         |
| - SELECT ... FOR UPDATE SKIP LOCKED                |  | - REST Endpoints for Incident Ops          |
| - Preempts Sev-3 tasks with Sev-1 priority batches |  | - SQL Analytics (MTTA, MTTR, Breach Rate)  |
+--------------------+-------------------------------+  +---------------------+----------------------+
                     |                                                         |
                     v                                                         v
+----------------------------------------------------+  +--------------------------------------------+
|         RAG & DETERMINISTIC RCA ENGINE             |  |         REACT 18 + TS FRONTEND             |
|                                                    |  |                                            |
| 1. pgvector Cosine Hybrid Search (Vector + SQL)    |  | - Discriminated Union diagnostic state     |
| 2. Deterministic Tool Registry (DB locks, metrics) |  | - AbortController race condition safety    |
| 3. Strict Pydantic RootCauseReport schema parse    |  | - Optimistic UI with rollback on failure   |
| 4. Audit Log entry generation                      |  | - Isolated SLA ticker (zero full re-render)|
+----------------------------------------------------+  +--------------------------------------------+
```

---

## Monorepo Directory Tree

```
traceguard/
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |   |-- v1/
|   |   |   |   |-- endpoints/
|   |   |   |   |   |-- alerts.py
|   |   |   |   |   |-- analytics.py
|   |   |   |   |   |-- auth.py
|   |   |   |   |   |-- incidents.py
|   |   |   |   |   +-- rca.py
|   |   |   |   +-- router.py
|   |   |   +-- deps.py
|   |   |-- core/
|   |   |   |-- config.py
|   |   |   |-- database.py
|   |   |   |-- redis.py
|   |   |   +-- security.py
|   |   |-- ingestion/
|   |   |   |-- base.py
|   |   |   |-- cloudwatch.py
|   |   |   |-- custom.py
|   |   |   |-- deduplicator.py
|   |   |   +-- prometheus.py
|   |   |-- models.py
|   |   |-- rca/
|   |   |   |-- tools/
|   |   |   |   |-- base.py
|   |   |   |   |-- db_locks.py
|   |   |   |   |-- deployments.py
|   |   |   |   |-- metrics.py
|   |   |   |   +-- registry.py
|   |   |   |-- engine.py
|   |   |   |-- indexer.py
|   |   |   +-- llm_adapter.py
|   |   |-- schemas.py
|   |   |-- workers/
|   |   |   +-- priority_worker.py
|   |   +-- main.py
|   |-- tests/
|   |   |-- conftest.py
|   |   |-- test_api.py
|   |   |-- test_dedup.py
|   |   |-- test_rag_rca.py
|   |   +-- test_worker.py
|   |-- Dockerfile
|   +-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |   +-- client.ts
|   |   |-- components/
|   |   |   |-- IncidentTable.tsx
|   |   |   |-- RCAInspectorDrawer.tsx
|   |   |   |-- SLAMetricsHeader.tsx
|   |   |   +-- Toast.tsx
|   |   |-- hooks/
|   |   |   |-- useIncidents.ts
|   |   |   +-- useSLACountdown.ts
|   |   |-- types/
|   |   |   +-- incident.ts
|   |   |-- App.tsx
|   |   |-- index.css
|   |   +-- main.tsx
|   |-- package.json
|   |-- tailwind.config.js
|   |-- tsconfig.json
|   +-- vite.config.ts
|-- docker-compose.yml
|-- INTERVIEW_MASTERGUIDE.md
+-- README.md
```

---

## Phase 1 Modules: Engineering Deep Dive

### 1. `backend/app/core/config.py`

#### The Engineering "Why"
- Pydantic Settings (`BaseSettings`) provides strict type enforcement on environment variables with cold-start validation. If an operational dependency like `POSTGRES_SERVER` or `SECRET_KEY` is missing or misformatted, the process fails fast during container boot rather than failing mid-flight during request processing.
- Dynamic `@computed_field` properties generate both asynchronous (`postgresql+asyncpg://`) and synchronous (`postgresql://`) connection URIs from a single source of truth, avoiding duplicate configuration fields that drift out of sync.

#### Failure Modes & Edge Cases
- Missing environment variables in production containers: Handled via defaults suitable for local development combined with explicit Docker Compose environment injection.
- Unset vector dimension: Defaults to 768 dimensions (compatible with standard embeddings). If the LLM embedding provider changes dimension, altering `VECTOR_DIMENSION` enforces schema validation.

#### Interview Questions & Answers
**Q1: Why separate the async and sync database connection strings in `config.py`?**
*Answer:* Asynchronous web workloads using FastAPI and SQLAlchemy 2.0 require the `asyncpg` driver to prevent blocking the Python asyncio event loop during I/O. However, migration tools (like Alembic) or certain synchronous debugging scripts require the standard `psycopg2` or synchronous dialect. Providing computed properties derived from isolated host, port, user, and password parameters ensures credentials remain synchronized across both execution models.

**Q2: How does Pydantic v2 Settings differ from manual `os.getenv` calls from an architectural perspective?**
*Answer:* `os.getenv` returns untyped strings or `None`, forcing defensive parsing and casting at every call site. If an integer like `SLA_MINUTES_SEV1` is assigned an invalid string, `os.getenv` defers the runtime failure until that variable is consumed inside business logic. Pydantic `BaseSettings` validates and coerces values at application instantiation, guaranteeing that all configuration consumed throughout the dependency graph adheres to invariant types.

**Q3: What security risk does storing default secret keys in `Settings` present, and how is it mitigated in production?**
*Answer:* Default keys embedded in source code allow anyone with repo access to forge JWT authentication tokens. In TraceGuard, the default key allows local zero-configuration development, but `SettingsConfigDict(env_file=".env")` ensures that production deployments override `SECRET_KEY` via injected container environment variables or cloud secret managers (e.g., AWS Secrets Manager, HashiCorp Vault).

---

### 2. `backend/app/core/database.py`

#### The Engineering "Why"
- `create_async_engine` with `pool_pre_ping=True` sends a lightweight `SELECT 1` ping on connection checkout. This eliminates transient connection errors caused by PostgreSQL closing idle connections or firewall drops behind cloud NAT gateways.
- `expire_on_commit=False` is mandatory in asynchronous SQLAlchemy. When SQLAlchemy commits a transaction, it normally expires all instance attributes so the next access reloads them from the database. In an async context, accessing an expired attribute outside an active greenlet context raises `sqlalchemy.orm.exc.MissingGreenlet`. Setting `expire_on_commit=False` allows callers to access model fields after commit without re-querying the database.

#### Failure Modes & Edge Cases
- Database connection starvation under traffic spikes: Mitigated by `pool_size=20` and `max_overflow=10`, allowing up to 30 concurrent connections before queuing requests.
- Async session leaks: The `get_db` async generator wraps session usage in a `try...finally` block, guaranteeing that `session.close()` is executed even if unhandled exceptions occur during HTTP request processing.

#### Interview Questions & Answers
**Q1: What is the cause of `sqlalchemy.orm.exc.MissingGreenlet: greenlet_spawn has not been called` in async FastAPI applications?**
*Answer:* This occurs when SQLAlchemy attempts to perform lazy-loading of an expired attribute or related relationship synchronously on an asyncio thread without an active async connection context. It commonly happens after `session.commit()` when `expire_on_commit=True`, or when accessing unloaded relationship attributes in Pydantic serializers. We prevent this by setting `expire_on_commit=False` and using explicit eager loading (`selectinload` or `joinedload`) for relationships.

**Q2: Why use `pool_pre_ping=True` instead of relying on pool recycle timeouts?**
*Answer:* `pool_recycle` only closes connections that have exceeded a fixed age. It does not protect against sudden server-side restarts, network partitions, or intermediate stateful firewall timeouts. `pool_pre_ping` validates connection viability at checkout with minimal overhead (`SELECT 1`), transparently evicting stale connections and opening fresh ones without bubbling 500 errors to the client.

**Q3: How does FastAPI's dependency injection system interact with the async generator `get_db()`?**
*Answer:* FastAPI's dependency resolver recognizes asynchronous generator functions (`async def get_db() -> AsyncGenerator`). When declared as a route dependency via `Depends(get_db)`, FastAPI executes the generator up to the `yield` statement, passes the active `AsyncSession` into the path operation, and resumes execution after the response is sent to run the `finally: await session.close()` block, guaranteeing transactional hygiene.

---

### 3. `backend/app/models.py`

#### The Engineering "Why"
- **Deterministic 64-character SHA-256 `fingerprint`:** Alert deduplication must be fast and storage-efficient. Instead of querying arbitrary text across variable payloads, a fixed-width indexed SHA-256 hash allows O(1) B-Tree lookups to detect duplicate incidents.
- **Composite Index `(status, severity, sla_deadline_at)`:**
  1. `status`: Low-cardinality equality filter (`WHERE status = 'TRIGGERED'`). Placing equality columns first maximizes index selectivity.
  2. `severity`: Filter or partition boundary (`WHERE severity = 'Sev-1'`).
  3. `sla_deadline_at`: Range scan and sort target (`ORDER BY sla_deadline_at ASC`). By placing the sort/range column last in the composite index, PostgreSQL performs an index-only scan, eliminating in-memory `filesort` execution plans.
- **HNSW Index for `pgvector`:**
  - `m=16`, `ef_construction=64`: Balances graph connectivity against index construction time and memory footprint.
  - Cosine distance (`vector_cosine_ops`): Runbook chunks vary in token length; cosine distance normalizes vector magnitude, comparing pure directional semantic similarity rather than Euclidean displacement.
- **SQLite JSON Variant:**
  - `JSONB().with_variant(JSON, "sqlite")`: Enables production deployment against PostgreSQL's high-performance binary JSON format (`JSONB`) while allowing fast in-memory SQLite test suites during CI without specialized extensions.

#### Failure Modes & Edge Cases
- Rapid duplicate alert bursts: Without fingerprint indexing, concurrent inserts would produce duplicate incident tickets. The indexed fingerprint combined with Redis deduplication and database uniqueness ensures at-most-once incident creation per sliding window.
- Missing `pgvector` library on minimal test environments: A fallback `UserDefinedType` mock allows static typing and local test runners to import `models.py` without requiring native PostgreSQL C-extensions.

#### Interview Questions & Answers
**Q1: Why did you choose HNSW over IVFFlat for the vector index on `runbook_chunks`?**
*Answer:* `IVFFlat` (Inverted File Flat) requires an upfront training step to cluster vectors into lists (`lists` parameter). If the index is queried before adequate data is loaded, or if data distributions drift, recall collapses unless the index is rebuilt. Furthermore, IVFFlat has lower query recall under high concurrency. `HNSW` (Hierarchical Navigable Small World) builds a multi-layer graph incrementally without a separate training step, provides high recall (>98%) out of the box, and supports concurrent inserts without index degradation.

**Q2: Explain the significance of column order in the composite index `(status, severity, sla_deadline_at)`.**
*Answer:* B-Tree composite indexes follow the left-to-right prefix rule. The SLA background worker and incident dashboard execute queries matching:
```sql
SELECT * FROM incidents 
WHERE status != 'RESOLVED' AND severity = 'Sev-1' 
ORDER BY sla_deadline_at ASC;
```
If `sla_deadline_at` were placed first, the engine would have to scan a range of dates and inspect every record's status and severity. By placing equality predicates (`status`, `severity`) first, the B-Tree traverses directly to the leaf page matching those values, then reads the already-sorted `sla_deadline_at` records sequentially, completely avoiding an expensive memory sort.

**Q3: Why use UUIDv4 for primary keys instead of auto-incrementing BIGINT sequence IDs?**
*Answer:* Auto-incrementing integers leak business volume metrics (e.g., total incidents created per day) and are vulnerable to enumeration attacks on public APIs. More importantly, in distributed architectures with worker pools and asynchronous ingestion pipelines, UUIDv4 allows client workers or ingestion nodes to generate unique identifiers locally before executing database writes, eliminating round-trips to acquire database sequence locks.

---

### 4. `backend/app/schemas.py`

#### The Engineering "Why"
- **Immutable Domain Model (`IncidentEvent` with `ConfigDict(frozen=True)`):** Once an incoming alert is parsed by an ingestion strategy, it represents a point-in-time domain event. Freezing the model prevents accidental mutation during deduplication, routing, or worker dispatch.
- **Deterministic Fingerprint Normalization:**
  ```python
  f"{service.strip().lower()}:{title.strip().lower()}:{environment.strip().lower()}"
  ```
  Alert titles often contain erratic spacing or capitalization depending on the monitoring source. Normalizing strings prior to hashing guarantees that `api-gateway:High CPU:production` and ` api-gateway : high cpu : PRODUCTION ` resolve to the identical SHA-256 fingerprint.
- **Strict Pydantic Constraints on `RootCauseReport`:**
  - `confidence_score: float = Field(..., ge=0.0, le=1.0)`
  - `supporting_evidence: List[str] = Field(..., min_length=1)`
  - `recommended_runbook_steps: List[str] = Field(..., min_length=1)`
  These constraints guarantee that LLM tool-calling output is validated deterministically before being persisted or delivered to the engineer. If an LLM hallucination returns an empty evidence list or an out-of-bounds confidence score, Pydantic raises a `ValidationError` at the boundary.

#### Failure Modes & Edge Cases
- Malformed hexadecimal strings supplied as fingerprints: `@field_validator("fingerprint")` validates 64 hexadecimal characters, rejecting invalid values before they reach database queries.
- Timestamp clock skew: Base SLA calculation defaults to explicit UTC `datetime.now(timezone.utc)`, preventing local timezone offset confusion between servers.

#### Interview Questions & Answers
**Q1: Why enforce `frozen=True` on the `IncidentEvent` Pydantic model?**
*Answer:* In event-driven and concurrent architectures, mutable state across async coroutines introduces subtle race conditions where one worker might mutate an alert payload while another is evaluating deduplication keys. Freezing the model enforces immutability; any attempt to reassign an attribute raises `ValidationError`. It also makes instances hashable and safe to pass across task boundaries.

**Q2: How does Pydantic v2's `from_attributes=True` (formerly `orm_mode=True`) operate under the hood with SQLAlchemy models?**
*Answer:* By default, Pydantic expects dictionary access (`obj["field"]`). SQLAlchemy model instances expose database columns as object attributes (`obj.field`). Setting `from_attributes=True` configures Pydantic's compiled Rust core (`pydantic-core`) to extract values via `getattr(obj, field)`, enabling direct conversion from SQLAlchemy ORM entities to serialization schemas without intermediate manual dictionary conversion.

**Q3: How does the schema architecture prevent LLM hallucinations from corrupting the database?**
*Answer:* The LLM does not execute direct database writes. Its response must conform to the strict `RootCauseReport` schema. If the model outputs malformed JSON, missing fields, a confidence score outside `[0.0, 1.0]`, or an empty list of supporting evidence, Pydantic's strict validation immediately rejects the payload. The failure is caught by our retry/fallback handler before any state change occurs in `rca_reports`.
