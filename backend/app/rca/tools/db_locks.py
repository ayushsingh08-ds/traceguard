from typing import Any, Dict
from app.rca.tools.base import DiagnosticTool


class CheckDatabaseLocksTool(DiagnosticTool):
    @property
    def name(self) -> str:
        return "check_database_locks"

    @property
    def description(self) -> str:
        return "Inspects active PostgreSQL locks, connection pool saturation, and blocked transactions."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service or database cluster to inspect.",
                },
                "min_lock_duration_seconds": {
                    "type": "integer",
                    "description": "Threshold for long-running transaction locks in seconds.",
                    "default": 10,
                },
            },
            "required": ["service"],
        }

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        service = kwargs.get("service", "unknown")
        min_lock_duration = kwargs.get("min_lock_duration_seconds", 10)

        is_db_service = any(db in service.lower() for db in ("db", "postgres", "order", "payment", "sql"))
        active_connections = 94 if is_db_service else 18
        max_connections = 100
        blocked_queries_count = 14 if is_db_service else 0

        blocked_tx = []
        if blocked_queries_count > 0:
            blocked_tx.append({
                "pid": 4821,
                "waiting_for_pid": 4802,
                "lock_type": "exclusive",
                "duration_seconds": max(min_lock_duration, 42),
                "query": "UPDATE orders SET status = 'PROCESSING' WHERE customer_id = $1 AND status = 'PENDING'",
            })
            blocked_tx.append({
                "pid": 4833,
                "waiting_for_pid": 4802,
                "lock_type": "exclusive",
                "duration_seconds": max(min_lock_duration, 38),
                "query": "SELECT * FROM inventory_items WHERE sku = $1 FOR UPDATE",
            })

        return {
            "service": service,
            "active_connections": active_connections,
            "max_connections": max_connections,
            "pool_saturation_pct": round((active_connections / max_connections) * 100, 1),
            "blocked_transactions_count": blocked_queries_count,
            "blocked_transactions": blocked_tx,
            "has_deadlock": blocked_queries_count > 10,
        }
