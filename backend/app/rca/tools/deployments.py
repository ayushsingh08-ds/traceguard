from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from app.rca.tools.base import DiagnosticTool


class InspectRecentDeploymentsTool(DiagnosticTool):
    @property
    def name(self) -> str:
        return "inspect_recent_deployments"

    @property
    def description(self) -> str:
        return "Inspects recent deployment rollouts, git commit SHAs, config changes, and pod crash loops."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the target microservice.",
                },
                "lookback_minutes": {
                    "type": "integer",
                    "description": "Minutes of historical deployments to scan.",
                    "default": 120,
                },
            },
            "required": ["service"],
        }

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        service = kwargs.get("service", "unknown")
        now = datetime.now(timezone.utc)
        deployed_at = now - timedelta(minutes=24)

        return {
            "service": service,
            "deployment_found": True,
            "latest_release": {
                "release_tag": "v2.14.0",
                "git_commit_sha": "7f8c92a1",
                "deployed_at": deployed_at.isoformat(),
                "author": "release-engineer@traceguard.internal",
                "change_summary": "Migrated connection pool timeout from 30s to 5s and adjusted thread limits",
            },
            "kubernetes_status": {
                "replicas_desired": 8,
                "replicas_ready": 6,
                "pod_crashloop_count": 2,
                "oom_killed_pods": 0,
                "last_container_exit_code": 137,
            },
            "is_suspect_deployment": True,
        }

