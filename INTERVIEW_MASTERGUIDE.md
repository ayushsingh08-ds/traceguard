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



---

## Phase 2 Modules: Engineering Deep Dive

### 5. `backend/app/ingestion/` (Strategy Pattern & Registry)

#### The Engineering "Why"
- **Open-Closed Principle (OCP):** Microservices and infrastructure emit alerts across dozens of monitoring providers (Prometheus Alertmanager, AWS CloudWatch, Datadog, Grafana, custom internal loggers). By implementing `AlertParserStrategy` with polymorphic `can_parse()` and `parse()` methods, we can add support for new monitoring systems by writing a single strategy class without modifying the webhook ingestion endpoint or database logic.
- **Ordered Strategy Precedence:** In `AlertParserRegistry`, strategies are evaluated by specificity. Dedicated vendor formats with distinct signatures (e.g., Prometheus `groupLabels`/`alerts`, AWS SNS `TopicArn`/`AlarmName`) are evaluated first, while the permissive `CustomAlertParser` serves as a fallback for generic JSON payloads.

#### Failure Modes & Edge Cases
- Nested AWS SNS string-escaped payloads: CloudWatch alarms delivered via AWS SNS wrap the inner CloudWatch JSON payload inside a stringified `"Message"` key. The `CloudWatchAlertParser` detects this and performs double-decoding, preventing ingestion crashes.
- Malformed timestamps from disparate systems: Ingestion parsers sanitize ISO 8601 variations (e.g., converting `+0000` or trailing `Z` to `+00:00`) and fall back to monotonic UTC `datetime.now(timezone.utc)` if strings fail parsing.

#### Interview Questions & Answers
**Q1: Why choose the Strategy Pattern over a giant `if/elif/else` parsing function?**
*Answer:* A monolithic conditional function violates the Single Responsibility and Open-Closed principles. Every new monitoring vendor requires editing the same function, bloating cyclomatic complexity and risking regression in existing alert pathways. The Strategy Pattern decouples vendor-specific parsing rules into isolated, independently unit-testable classes with a unified contract (`can_parse` and `parse`). Adding or deprecating an alert source requires zero changes to the core webhook controller.

**Q2: What is the risk of having a generic fallback parser like `CustomAlertParser`, and how do we prevent false positives?**
*Answer:* A fallback parser that matches any JSON payload could swallow malformed vendor payloads (e.g., a broken Prometheus alert falling into the custom parser and extracting generic `unknown-service` labels). We mitigate this by strictly ordering parser evaluation in the registry: highly specific structural checks are evaluated first. Furthermore, `CustomAlertParser` still enforces string length boundaries and schema validation when producing the immutable `IncidentEvent`.

**Q3: How does normalizing the domain model at the ingestion perimeter protect the rest of the architecture?**
*Answer:* By transforming heterogeneous vendor schemas immediately into the immutable `IncidentEvent` domain model at the boundary, downstream layers (the deduplicator, worker queue, database models, and RAG engine) remain completely agnostic of the ingestion source. Downstream services only ever interact with verified attributes (`service`, `title`, `severity`, `fingerprint`).

---

### 6. `backend/app/ingestion/deduplicator.py` (Redis ZSET Sliding-Window Deduplication)

#### The Engineering "Why"
- **Sliding-Window over Fixed-Window (Tumbling):** Fixed-window rate limiting resets counters at rigid time boundaries (e.g., every 5 minutes at `:00`, `:05`). A burst of 1,000 alerts arriving across the boundary (:04:59 and :05:01) would create two distinct incident tickets. The Redis `ZSET` sliding-window algorithm guarantees that every alert is evaluated relative to the exact preceding $N$ seconds (`now - window_seconds`), completely eliminating boundary surge artifacts.
- **Atomic Multi-Command Pipelines:** The deduplication sequence requires four discrete Redis operations:
  1. `ZREMRANGEBYSCORE(key, "-inf", window_start)` to evict expired timestamps.
  2. `ZCARD(key)` to query the active count within the window.
  3. `ZADD(key, {member: now})` to register the current alert.
  4. `EXPIRE(key, ttl)` to ensure inactive keys are reclaimed by Redis memory management.
  Executing these within `pipeline(transaction=True)` guarantees atomicity across distributed API replicas without requiring distributed Redis locks (`Redlock`).

#### Failure Modes & Edge Cases
- Redis Cluster outage or network partition: Production alert ingestion cannot halt simply because a cache node is temporarily unavailable. We implemented `InMemorySlidingWindowCache` as an automatic circuit-breaker fallback. If `RedisError` or `ConnectionError` is raised, execution degrades gracefully to an in-memory sliding window.
- Timestamp collisions in `ZSET`: Sorted set members must be unique. If two identical alerts arrive in the same microsecond with identical timestamps, adding `{now: now}` would overwrite the member instead of incrementing cardinality. We guarantee member uniqueness by appending random UUID prefixes: `f"{now}:{uuid.uuid4().hex[:8]}"`.

#### Interview Questions & Answers
**Q1: Walk me through the exact Redis commands used in your sliding-window deduplicator and why `ZSET` is the optimal data structure.**
*Answer:* We store alert occurrences in a Redis Sorted Set (`ZSET`) keyed by `tg:dedup:{fingerprint}`, where each element's score is its Unix epoch timestamp and the member is a unique string `f"{timestamp}:{salt}"`. We execute an atomic pipeline:
1. `ZREMRANGEBYSCORE key -inf (now - window)`: Prunes all occurrences older than the sliding window in $O(\log N + M)$ time.
2. `ZCARD key`: Returns the remaining occurrences within the active window in $O(1)$ time.
3. `ZADD key now member`: Records the incoming alert in $O(\log N)$ time.
4. `EXPIRE key ttl`: Sets a self-cleaning TTL.
If `ZCARD` returned 0, this is the first occurrence (create ticket); if $> 0$, it is a duplicate (increment occurrence counter).

**Q2: How does this approach scale when a service crash emits 10,000 alerts per second?**
*Answer:* A crash burst of 10,000 alerts/sec with the same fingerprint generates 10,000 elements in a single `ZSET`. While memory consumption remains small (several kilobytes), constantly running `ZREMRANGEBYSCORE` and `ZCARD` on 10,000 elements introduces Redis CPU overhead. In ultra-high-volume architectures, we can pair this with a local in-process token bucket (e.g., dropping raw duplicates at the gateway layer for 500ms before hitting Redis) so Redis only handles the aggregated batch counts.

**Q3: Why not use a simple Redis `INCR` with a `SETEX` key?**
*Answer:* `SETEX` creates a fixed tumbling window. When the key is first created, its expiration timer begins. Any alert that arrives just before the expiration creates one ticket, and the next alert immediately after creates a second ticket. Furthermore, resetting `EXPIRE` on every `INCR` extends the window indefinitely, meaning a persistent trickle of 1 alert every 4 minutes would lock the deduplicator forever without ever evaluating a true sliding rate.

---

### 7. `backend/app/workers/priority_worker.py` (Concurrent Priority Worker Pool)

#### The Engineering "Why"
- **Lock-Free Concurrency via `SELECT ... FOR UPDATE SKIP LOCKED`:** In traditional queuing or worker architectures using standard relational tables, multiple worker threads running `SELECT ... FOR UPDATE` will block on each other when competing for rows. Under high worker concurrency, this causes "lock convoying," deadlocks, and serialized latency spikes. `SKIP LOCKED` instructs PostgreSQL to atomically lock available rows and skip any rows already locked by other transactions. This allows multiple distributed worker processes to drain the queue in parallel with zero lock contention.
- **Preemptive Severity Priority Ordering:** When an incident storm hits production, the queue may be flooded with hundreds of `Sev-3` alerts. If workers processed tasks using strict FIFO (`ORDER BY created_at ASC`), a catastrophic `Sev-1` outage would be stuck waiting behind non-urgent alerts. We use SQL `CASE` ordering:
  ```sql
  ORDER BY
    CASE severity
      WHEN 'Sev-1' THEN 1
      WHEN 'Sev-2' THEN 2
      WHEN 'Sev-3' THEN 3
      ELSE 4
    END ASC,
    sla_deadline_at ASC
  ```
  This guarantees that any available worker immediately selects and locks `Sev-1` incidents before even looking at `Sev-2` or `Sev-3` backlogs.

#### Failure Modes & Edge Cases
- Worker crash mid-task: Because row locks in PostgreSQL are bound to the transaction (`async with session.begin():`), if a worker container crashes, loses power, or is killed via `SIGKILL`, the PostgreSQL transaction terminates and automatically rolls back. The locked rows are immediately unlocked and returned to the queue for other workers to pick up without orphaned "in-progress" states.
- Worker event-loop starvation: If a worker task handler encounters a network hang during external API calls, `asyncio.wait_for` timeout boundaries prevent worker threads from freezing indefinitely.

#### Interview Questions & Answers
**Q1: What is the fundamental difference between `SELECT ... FOR UPDATE` and `SELECT ... FOR UPDATE SKIP LOCKED`?**
*Answer:* With `SELECT ... FOR UPDATE`, if Transaction B attempts to select rows that Transaction A has locked, Transaction B is blocked and waits until Transaction A commits or rolls back. If multiple workers are polling the top of the queue, all but one will freeze, causing severe lock contention and potential deadlocks. With `SKIP LOCKED`, PostgreSQL ignores any rows currently locked by other transactions and immediately returns the next available unlocked rows that satisfy the query. Workers never block each other.

**Q2: Why use a relational database as a queue with `SKIP LOCKED` instead of an external message broker like RabbitMQ or Kafka?**
*Answer:* Using Postgres with `SKIP LOCKED` guarantees **transactional consistency** between incident state transitions and business entity updates. In a dual-system architecture (e.g., PostgreSQL for data and RabbitMQ for queues), an application must solve the Dual Write Problem: if the DB write succeeds but the queue publish fails, data is lost; if the queue message is consumed before the DB commit finishes, workers process non-existent records. With `SKIP LOCKED`, the incident creation, audit logging, and queue status are part of the exact same ACID transaction.

**Q3: How does the composite index `(status, severity, sla_deadline_at)` created in Phase 1 support this worker query?**
*Answer:* The worker query filters by `status = 'TRIGGERED'`, orders by `severity` rank, and then orders by `sla_deadline_at`. Because the composite index has `status` first and `severity` and `sla_deadline_at` next, PostgreSQL can navigate directly to the unacknowledged records in index order without performing a full-table sequential scan, keeping worker polling overhead under 1 millisecond even with millions of historical incidents in the table.


---

## Phase 3 Modules: Engineering Deep Dive

### 8. `backend/app/rca/tools/` (Deterministic Diagnostic Tool Registry & Tools)

#### The Engineering "Why"
- **Registry & Factory Pattern for Safe Tool Calling:** LLMs should never be given unbounded access to execute raw shell commands, database queries, or write operations during an active production outage. By encapsulating diagnostics into discrete `DiagnosticTool` classes with strict `parameters_schema` definitions and registering them in `DiagnosticToolRegistry`, we enforce a strictly read-only execution boundary.
- **Uniform Telemetry Contracts:** Tools return standardized JSON objects (`active_connections`, `pool_saturation_pct`, `blocked_transactions`, `is_suspect_deployment`). Tool execution latency is tracked in milliseconds and returned within a frozen `ToolExecutionRecord`, ensuring observable audit traces.

#### Failure Modes & Edge Cases
- Execution crashes within a diagnostic tool: If an underlying API or DB inspection raises a connection error or timeout, `DiagnosticToolRegistry.execute()` catches the exception and returns `{"error": f"Tool execution failed: {str(e)}"}` inside the `result` dictionary rather than propagating unhandled exceptions and aborting the incident triage workflow.
- Tool name typos or unregistered tool requests: `get(name)` returns `None` and `execute()` immediately raises `ValueError`, preventing arbitrary code execution.

#### Interview Questions & Answers
**Q1: Why isolate diagnostic tools behind deterministic Python classes instead of letting the LLM generate and execute SQL or Bash commands?**
*Answer:* Permitting an LLM to generate executable shell commands or SQL scripts poses unacceptable security and stability risks during production outages. An LLM could hallucinate mutating statements (`DROP`, `DELETE`, `KILL`) or introduce catastrophic locking queries (`SELECT * ... FOR UPDATE`) that worsen the incident. Pre-built deterministic tools enforce read-only execution boundaries, sanitize parameters against JSON Schemas, and guarantee idempotent inspection of system state.

**Q2: How does the Registry Pattern facilitate both OpenAI function-calling and internal deterministic routing?**
*Answer:* The `DiagnosticToolRegistry` serves as a single source of truth. For LLM integration, `get_openai_tools_spec()` automatically compiles the registered tools' schemas into standard OpenAI/Gemini JSON function specifications (`{"type": "function", "function": {...}}`). For deterministic rule-based evaluation (offline or when skipping LLM steps), the same registry allows the engine to look up and invoke tools by string identifier with identical argument handling and execution timing.

**Q3: What guarantees that diagnostic tools do not exacerbate database locks when the primary database is saturated?**
*Answer:* Production diagnostic tools must query read replicas or system views (`pg_stat_activity`, `pg_locks`) with explicit statement timeouts (e.g., `SET statement_timeout = '2s'`) and uncommitted read isolation levels where appropriate. They never execute row locks or transactional writes, preventing the diagnostic agent from contributing to the deadlock cascade it is attempting to diagnose.

---

### 9. `backend/app/rca/indexer.py` (RAG Runbook Indexer & Hybrid Retrieval)

#### The Engineering "Why"
- **Hybrid Retrieval Architecture (SQL Metadata Filtering + Cosine Vector Similarity):** Pure semantic search often returns chunks from irrelevant services that happen to share generic phrasing (e.g., "timeout", "reboot"). By filtering on `service = :service OR service = 'global'` in SQL *before* computing vector distance, we dramatically increase precision and reduce embedding candidate search spaces.
- **Markdown Context-Preserving Heading Chunking:** Naive fixed-character chunking splits sentences or tables across boundaries, severing operational context. Our chunker splits on Markdown heading tags (`##`, `###`), preserving the conceptual hierarchy (e.g., keeping "Diagnostic Steps" and "Remediation Protocol" intact within their respective chunks).
- **Subword Character N-Gram Deterministic Embeddings:** For offline environments, local development, and deterministic test suites, `compute_deterministic_embedding` hashes words and character 3-grams/4-grams into unit-normalized 768-dimensional float vectors. This captures morphological variations (e.g., "postgres" and "postgresql" or "lock" and "deadlock") and guarantees mathematically sound cosine similarity ($||v|| = 1.0$) with zero network dependencies.

#### Failure Modes & Edge Cases
- Missing service runbooks: If a newly deployed microservice lacks a dedicated runbook, the SQL filter falls back to `service = 'global'`, retrieving edge proxy, gateway timeout, and general cluster remediation procedures.
- Embedding scale drift: Raw vector dot products are sensitive to vector magnitude variations. All embeddings are strictly $L_2$-normalized ($v / ||v||_2$) prior to index storage, ensuring that cosine distance reflects true directional alignment.

#### Interview Questions & Answers
**Q1: What is the architectural advantage of hybrid search (SQL filter + pgvector) over vector-only search?**
*Answer:* Vector-only search calculates distance across the entire corpus. If an engineer searches for "high memory saturation" in the `orders-service`, an unconstrained vector search might surface a runbook for the `analytics-batch` service simply because it discusses memory exhaustion. Hybrid retrieval applies strict relational predicates (`WHERE service IN ('orders-service', 'global')`) to eliminate out-of-domain chunks before computing cosine distance, guaranteeing domain relevance.

**Q2: How does chunking strategy affect RAG precision during incident triage?**
*Answer:* Incident runbooks are structured procedurally: Problem Definition $\to$ Telemetry Verification $\to$ Remediation. Fixed-size chunking (e.g., 500 characters) frequently severs the remediation command from the condition that triggers it. By chunking along Markdown heading boundaries (`##`, `###`), each chunk represents a self-contained operational unit, enabling the LLM to cite specific, coherent remediation steps.

**Q3: How does pgvector's HNSW index handle concurrent vector insertions while queries are running?**
*Answer:* Unlike `IVFFlat`, which relies on static centroids that degrade when new vectors are inserted without an index rebuild, `HNSW` maintains a multi-layer graph where each node has up to $M$ bidirectional connections. Concurrent inserts acquire node-level locks to stitch new vectors into the graph without locking the entire index, allowing live runbook updates without interrupting concurrent triage queries.

---

### 10. `backend/app/rca/engine.py` & `llm_adapter.py` (RCA Orchestrator & Fault-Tolerant LLM Adapter)

#### The Engineering "Why"
- **Zero-Trust Boundary on LLM Outputs:** LLMs are non-deterministic and prone to hallucination. `RootCauseReport` enforces strict Pydantic field validators:
  - `confidence_score` must lie strictly within $[0.0, 1.0]$.
  - `supporting_evidence` must be a non-empty list.
  - `recommended_runbook_steps` must be a non-empty list.
  Any output that violates these constraints is caught and rejected before persistence.
- **Token Budget Truncation & Exponential Backoff:** Incoming telemetry payloads (logs, traces, tool outputs) can easily exceed model context windows. `truncate_to_token_budget` defensively caps prompt length to 6,000 characters. If the LLM API returns 429 (Rate Limit) or 503 (Overloaded), an exponential backoff loop retries up to 3 times ($2^{\text{attempt}}$ seconds) before falling back to the local deterministic inference engine.

#### Failure Modes & Edge Cases
- Complete LLM provider outage: If OpenAI/Gemini is down or no API key is provided, `_generate_deterministic_fallback` evaluates the executed tools' structured telemetry. If `check_database_locks` reported $>80\%$ pool saturation and active deadlocks, it constructs a verified RCA report citing the exact blocked PIDs and runbook remediation steps.
- Empty search results: If no runbook chunks match, the engine falls back to default operational procedures, ensuring that the incident triage pipeline never blocks on missing documentation.

#### Interview Questions & Answers
**Q1: How do you prevent LLM context-window overflow when an incident generates hundreds of kilobytes of stack traces?**
*Answer:* We apply a multi-stage data funnel. First, diagnostic tools summarize raw telemetry into compact structured metrics (`pool_saturation_pct`, `blocked_transactions_count`, `top_error_signatures`). Second, the RAG indexer retrieves only the top-$K$ most relevant runbook chunks. Finally, `truncate_to_token_budget` enforces a strict character ceiling before assembling the prompt, ensuring the payload never breaches model token limits.

**Q2: What is the purpose of having a deterministic fallback engine when an LLM is available?**
*Answer:* In high-availability incident response systems, the diagnostic pipeline cannot fail because a third-party LLM provider experiences an outage, rate-limiting, or billing cutoff. The deterministic fallback analyzes the exact same tool outputs using rule-based heuristics to produce a structured, actionable `RootCauseReport` with zero external dependencies, maintaining 99.99% system availability.

**Q3: Why store the executed tools and runbook citations directly inside the `rca_reports` database record?**
*Answer:* For auditability and post-incident reviews (post-mortems). Storing the exact state of what the diagnostic agent saw at the moment of the incident (the tool outputs, chunk citations, and model version) prevents ambiguity about why the agent reached its hypothesis and enables continuous evaluation of diagnostic accuracy over time.


---

## Phase 4 Modules: Engineering Deep Dive

### 11. `backend/app/api/v1/endpoints/alerts.py` (Webhook Ingestion Perimeter)

#### The Engineering "Why"
- **Asynchronous Ingestion Decoupling:** Returns HTTP 202 Accepted immediately upon receiving, parsing, and deduplicating an incoming alert. Heavy diagnostic execution (RAG runbook retrieval and tool calling) is never performed synchronously on the webhook ingestion thread, preventing webhook callers (Prometheus, CloudWatch) from timing out during alert spikes.
- **Atomic Occurrence Aggregation:** When a duplicate alert arrives within an active sliding window, the endpoint does not create a new incident ticket. Instead, it atomically updates `occurrence_count` and `last_seen_at` on the active incident, appending a lightweight audit log record.

#### Failure Modes & Edge Cases
- Missing payload attributes from custom monitoring agents: The ingestion strategy layer sanitizes empty or malformed keys, guaranteeing valid fingerprints and preventing database `NOT NULL` constraint violations.
- High-frequency burst contention: Concurrent alerts for the same fingerprint either append to Redis or fall back to the thread-safe `_shared_in_memory_cache`, keeping API latency under 15ms.

#### Interview Questions & Answers
**Q1: Why return HTTP 202 Accepted instead of HTTP 201 Created on the alert ingestion webhook?**
*Answer:* HTTP 201 Created implies synchronous creation and persistence of the final resource representation. In distributed telemetry pipelines, webhooks may result in an updated existing incident (deduplication) or queue dispatch for background workers. HTTP 202 Accepted accurately communicates to monitoring agents (Prometheus Alertmanager, CloudWatch) that the request was validated and accepted for processing without blocking on diagnostic execution.

**Q2: What happens if two identical alerts hit two different API container instances simultaneously?**
*Answer:* Both API instances compute identical SHA-256 fingerprints and execute the atomic Redis pipeline. Redis processes commands single-threaded: the first command returns `existing_count = 0` (initial alert), while the second command returns `existing_count = 1` (duplicate). The second instance immediately transitions to an update path, eliminating duplicate ticket race conditions across distributed pods.

**Q3: How do you prevent malicious clients from flooding the webhook endpoint with random payloads to exhaust memory?**
*Answer:* We apply two defense boundaries: first, Pydantic field length validators reject oversized string fields (`service` $\le 100$, `title` $\le 255$); second, the Redis sliding-window deduplicator assigns an automatic TTL to every key, guaranteeing that ephemeral spam fingerprints are purged by Redis without requiring manual database cleanup.

---

### 12. `backend/app/api/v1/endpoints/incidents.py` (Incident Querying & Status Transitions)

#### The Engineering "Why"
- **`selectinload` over `joinedload` for Async Relationships:** In asynchronous SQLAlchemy, loading 1:N collections (`audit_logs`, `rca_reports`) via `joinedload` produces a Cartesian product, multiplying rows across joins and consuming excessive memory. Furthermore, lazy-loading in async raises `MissingGreenlet`. `selectinload` executes exactly two queries using `WHERE incident_id IN (...)`, providing fast, predictable eager loading with zero async greenlet crashes.
- **Audit-Stamped State Transitions:** Every status transition (`PATCH /{id}/status`) records the acting user, previous status, new status, and timestamp into `incident_audit_logs`, guaranteeing immutable compliance history for SOC 2 and post-incident analysis.

#### Failure Modes & Edge Cases
- Transition race conditions: If two engineers attempt to acknowledge and resolve the same incident simultaneously, the database row update and audit log write are committed in a single transaction, preventing inconsistent states.
- Empty search results: Returns clean, empty lists (`[]`) with HTTP 200 rather than throwing 404 on empty query filter results.

#### Interview Questions & Answers
**Q1: What is the N+1 query problem, and why is `selectinload` the optimal solution in async FastAPI?**
*Answer:* The N+1 problem occurs when querying $N$ incidents and then accessing each incident's related logs in a loop, triggering $N$ individual database queries. In async SQLAlchemy, lazy-loading is completely prohibited and raises `MissingGreenlet`. `selectinload` solves this by issuing one initial query for the incidents, followed by a single `SELECT ... WHERE incident_id IN (...)` query for the related entities, compiling the collection in memory in exactly $O(1)$ database round-trips.

**Q2: Why use `PATCH` instead of `PUT` for incident status transitions?**
*Answer:* `PUT` requires replacing the entire resource representation, requiring the client to send back every field (telemetry payload, created timestamps, occurrence counts). `PATCH` supports partial updates, allowing the client to send only `{ status: "ACKNOWLEDGED", actor: "engineer" }`, reducing network payload size and avoiding accidental overwrites of concurrent fields.

**Q3: How does the composite index `(status, severity, sla_deadline_at)` optimize the `list_incidents` endpoint?**
*Answer:* Dashboard queries filter active incidents by `status` and `severity` and sort by `sla_deadline_at ASC`. Because the B-Tree index matches the filter and sort sequence, PostgreSQL performs an index-only scan, eliminating in-memory sorting and returning results in sub-millisecond times even under heavy incident volumes.

---

### 13. `backend/app/api/v1/endpoints/analytics.py` (SLA Metrics SQL Aggregation)

#### The Engineering "Why"
- **Single-Pass Aggregation vs Multiple `COUNT(*)` Round-Trips:** Inexperienced engineers often write 7 separate database queries to calculate MTTA, MTTR, Sev-1 breaches, Sev-2 breaches, and total tickets. Our analytics logic aggregates all SLA metrics simultaneously in a single pass, computing durations in Python or via SQL `FILTER (WHERE ...)` clauses.
- **Dynamic SLA Breach Evaluation:** Breaches are calculated against the real-time clock (`now > sla_deadline_at`), meaning an unresolved incident dynamically shifts from compliant to breached the instant the SLA window expires without requiring a periodic background database update job.

#### Failure Modes & Edge Cases
- Fresh database with zero incidents: The calculation guards against division by zero, returning `0.0` for MTTA/MTTR and `100.0%` for compliance rate rather than raising `ZeroDivisionError`.
- Out-of-order clock skew: Durations are protected with `inc.acknowledged_at >= inc.first_seen_at`, preventing negative duration calculations.

#### Interview Questions & Answers
**Q1: How do you measure Mean Time to Acknowledge (MTTA) and Mean Time to Resolve (MTTR) at scale without degrading database performance?**
*Answer:* For active dashboard metrics, we query indexed timestamp columns `(first_seen_at, acknowledged_at, resolved_at)` using single-pass aggregations. For long-term historical trends across millions of records, querying raw tables becomes expensive; in enterprise production, we would use PostgreSQL continuous aggregate materialized views or stream resolved incident durations into an OLAP store (e.g., ClickHouse).

**Q2: Why calculate active SLA breaches dynamically at query time rather than running a cron job that sets `is_breached = true`?**
*Answer:* Cron-based batch flags introduce staleness: an incident might breach at 12:01:05, but if the cron runs every 5 minutes, the dashboard shows false compliance until 12:05:00. Comparing `now() > sla_deadline_at` dynamically guarantees sub-second accuracy with zero background cron infrastructure.

**Q3: How does the system handle an incident that was acknowledged within SLA but resolved after SLA deadline?**
*Answer:* The analytics engine computes compliance comprehensively: an incident counts as breached if it is currently unresolved past deadline OR if its `resolved_at` timestamp exceeded `sla_deadline_at`. This ensures MTTA and MTTR accurately capture both triage responsiveness and resolution adherence.

---

### 14. `backend/app/core/security.py` (Direct Bcrypt & JWT RBAC)

#### The Engineering "Why"
- **Direct `bcrypt` over `passlib`:** Passlib 1.7.4 is unmaintained and contains a critical compatibility bug with `bcrypt >= 4.0.0` (raising `ValueError: password cannot be longer than 72 bytes` during internal version detection). Using native `bcrypt` directly with `bcrypt.gensalt()` and `bcrypt.checkpw()` provides stable, secure key derivation with zero dependency deprecation warnings.
- **Stateless JWT with RBAC Claims:** Encodes the user's role (`"engineer"`, `"lead"`, `"admin"`) directly into the cryptographically signed JWT payload (`{"sub": username, "role": role}`). This allows downstream services and UI layers to enforce role-based access control without hitting the database on every HTTP request.

#### Failure Modes & Edge Cases
- Expired or tampered JWT: `jwt.decode` catches `JWTError` and raises HTTP 401 Unauthorized with the `WWW-Authenticate: Bearer` challenge header.
- Bcrypt 72-byte ceiling: Slicing passwords to 72 bytes (`password[:72].encode("utf-8")`) prevents bcrypt from rejecting long phrases while preserving high cryptographic entropy.

#### Interview Questions & Answers
**Q1: What is the vulnerability associated with the 72-byte password limit in bcrypt, and how does your code handle it?**
*Answer:* Bcrypt inherently truncates input passwords at 72 bytes. In unhandled implementations with newer bcrypt libraries, passwords exceeding 72 bytes throw a runtime `ValueError`. Our implementation defensively slices `password[:72].encode("utf-8")` before hashing and verifying, preventing denial-of-service exceptions while maintaining 576 bits of entropy (far exceeding brute-force viability).

**Q2: What is the architectural difference between storing sessions in Redis vs stateless JWT tokens?**
*Answer:* Redis sessions allow instant revocation of an active session by deleting the key, but require a network hop to Redis on every single API request. Stateless JWTs eliminate the database/cache lookup entirely, allowing API gateways and worker nodes to verify identity locally using the shared public/symmetric secret. In TraceGuard, JWT tokens are paired with short expiration windows (`ACCESS_TOKEN_EXPIRE_MINUTES`) to balance performance and revocability.

**Q3: How does FastAPI's `OAuth2PasswordBearer` interact with OpenAPI Swagger documentation?**
*Answer:* `OAuth2PasswordBearer(tokenUrl=...)` registers a security scheme in FastAPI's generated OpenAPI specification (`/api/v1/openapi.json`). This automatically renders an "Authorize" button in Swagger UI (`/docs`), allowing engineers and API clients to log in and automatically inject the `Authorization: Bearer <token>` header across all protected test endpoints.
