# TraceGuard: High-Throughput Incident Triage, SLA Tracker & RAG Diagnostics Engine

TraceGuard is a production-grade developer platform engineered to ingest high-velocity infrastructure alerts, suppress noisy duplicate spikes via Redis sliding-window algorithms, prioritize Sev-1 incidents using PostgreSQL lock-free queues (`SELECT ... FOR UPDATE SKIP LOCKED`), and orchestrate automated Root Cause Analysis (RCA) combining `pgvector` hybrid semantic search with deterministic system diagnostic tools.

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

## Technical Highlights

### 1. Ingestion Strategy Pattern & Alert Deduplication
- **Strategy Pattern:** Normalizes webhook payloads from Prometheus Alertmanager, AWS CloudWatch (including nested SNS string envelopes), and custom microservice logs into an immutable `IncidentEvent` model.
- **Redis Sorted Set (`ZSET`) Sliding-Window Deduplicator:** When a service crash triggers 1,000 alerts per second with the same signature, TraceGuard hashes `lowercase(service:title:environment)` into a 64-character SHA-256 fingerprint. An atomic pipeline (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE`) creates only one ticket and increments an `occurrence_count` counter. An in-memory cache acts as a circuit breaker fallback if Redis is unreachable.

### 2. Lock-Free Priority Worker Queue
- **Concurrency Architecture:** Multiple worker coroutines poll PostgreSQL using `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Preemptive Severity Dispatch:** Uses SQL `CASE` ordering so that incoming `Sev-1` incidents immediately preempt `Sev-3` queues without worker thread starvation or database lock convoying.

### 3. Database Indexing & SQL Analytics
- **Composite Index Ordering:** `ix_incidents_status_severity_sla_deadline` follows the left-to-right rule `(status, severity, sla_deadline_at)`. Equality predicates (`status`, `severity`) precede the range/sort target (`sla_deadline_at`), allowing PostgreSQL to eliminate in-memory `filesort` passes.
- **Single-Pass SLA Analytics:** Calculates Mean Time to Acknowledge (MTTA), Mean Time to Resolve (MTTR), active SLA breach counts, and compliance rate simultaneously using single-pass aggregations.

### 4. Hallucination-Resistant GenAI Diagnostics
- **Hybrid RAG Retrieval:** Queries `pgvector` HNSW indexes with SQL metadata filtering (`service = :service OR service = 'global'`) before computing cosine distance over Markdown runbooks.
- **Deterministic Diagnostic Tools:** Pre-registered read-only tools inspect database lock metrics, Kubernetes deployment rollouts, and telemetry error spikes.
- **Zero-Trust Validation:** The LLM adapter enforces strict Pydantic bounds (`confidence_score` $\in [0.0, 1.0]$, non-empty evidence lists, token budget truncation) and falls back to a deterministic inference engine if the LLM API is unavailable.

### 5. Frontend Architecture
- **Strict TypeScript & Discriminated Unions:** Models the diagnostic lifecycle as `{ status: 'idle' } | { status: 'running'; activeTool: string } | { status: 'completed'; report: RootCauseReport } | { status: 'failed'; error: string }`, preventing invalid states at compile time.
- **Race-Condition Safety:** `useIncidents.ts` uses `AbortController` inside `useEffect` to abort in-flight requests during rapid filter toggling.
- **Isolated SLA Countdown Ticker:** `useSLACountdown.ts` isolates 1-second interval ticks to individual badge elements, preventing expensive full-table re-renders.
- **Optimistic UI with Rollback:** Status transitions (`ACKNOWLEDGE`, `RESOLVE`) mutate local state immediately, rolling back cleanly if the server rejects the request.

---

## Repository Structure

```
traceguard/
|-- backend/
|   |-- app/
|   |   |-- api/v1/endpoints/   # alerts, incidents, rca, analytics, auth
|   |   |-- core/               # config, database, redis, security
|   |   |-- ingestion/          # Strategy pattern parsers and Redis deduplicator
|   |   |-- models.py           # SQLAlchemy 2.0 ORM + pgvector DDL
|   |   |-- rca/                # RAG runbook indexer, tool registry, and RCA engine
|   |   |-- schemas.py          # Pydantic v2 domain schemas and contracts
|   |   |-- workers/            # Async priority worker (SELECT FOR UPDATE SKIP LOCKED)
|   |   +-- main.py             # FastAPI entrypoint and lifespan management
|   |-- tests/                  # 19 passing unit and integration tests
|   |-- Dockerfile
|   +-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- api/client.ts       # Zero-dependency fetch client with JWT interceptor
|   |   |-- components/         # IncidentTable, RCAInspectorDrawer, SLAMetricsHeader, Toast
|   |   |-- hooks/              # useIncidents (AbortController), useSLACountdown (isolated ticker)
|   |   |-- types/incident.ts   # Discriminated unions and domain contracts
|   |   |-- App.tsx
|   |   +-- main.tsx
|   |-- Dockerfile
|   +-- package.json
|-- docker-compose.yml
|-- INTERVIEW_MASTERGUIDE.md    # Complete architectural defense and interview guide
+-- README.md
```

---

## Local Development & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional for full-stack containerization)

### Option 1: Docker Compose (Recommended)
```bash
docker compose up --build
```
- Frontend: `http://localhost:3000`
- Backend API Docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

### Option 2: Local Manual Setup

#### 1. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### 2. Run Backend Tests
```bash
python -m pytest
```

#### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/alerts/webhook` | Ingests monitoring webhooks (Prometheus, CloudWatch, Custom) with deduplication |
| `GET` | `/api/v1/incidents` | Lists active incidents with status, severity, and service filters |
| `GET` | `/api/v1/incidents/{id}` | Retrieves full incident detail with eager-loaded audit logs and RCA reports |
| `PATCH` | `/api/v1/incidents/{id}/status` | Optimistic status update (`ACKNOWLEDGED`, `RESOLVED`) with audit log stamping |
| `POST` | `/api/v1/rca/{id}/diagnose` | Triggers RAG runbook search and diagnostic tool-calling RCA pipeline |
| `GET` | `/api/v1/rca/{id}/report` | Retrieves the latest structured RCA report for an incident |
| `GET` | `/api/v1/analytics/sla` | Computes real-time MTTA, MTTR, active breach counts, and SLA compliance |
| `POST` | `/api/v1/auth/login` | Returns JWT Bearer token |
| `GET` | `/health` | Service health status check |

