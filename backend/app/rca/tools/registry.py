import time
from typing import Any, Dict, List, Optional

from app.rca.tools.base import DiagnosticTool
from app.rca.tools.db_locks import CheckDatabaseLocksTool
from app.rca.tools.deployments import InspectRecentDeploymentsTool
from app.rca.tools.metrics import QueryErrorRateSpikeTool
from app.schemas import ToolExecutionRecord


class DiagnosticToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, DiagnosticTool] = {}
        # Pre-register deterministic production diagnostic tools
        self.register(CheckDatabaseLocksTool())
        self.register(InspectRecentDeploymentsTool())
        self.register(QueryErrorRateSpikeTool())

    def register(self, tool: DiagnosticTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[DiagnosticTool]:
        return self._tools.get(name)

    def get_all(self) -> List[DiagnosticTool]:
        return list(self._tools.values())

    def get_openai_tools_spec(self) -> List[Dict[str, Any]]:
        # Translates internal tool abstractions into standard JSON Schema function specifications
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, **kwargs: Any) -> ToolExecutionRecord:
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Diagnostic tool '{name}' is not registered in the tool registry")

        start_time = time.perf_counter()
        try:
            result = await tool.execute(**kwargs)
        except Exception as e:
            result = {"error": f"Tool execution failed: {str(e)}"}
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return ToolExecutionRecord(
            tool_name=name,
            parameters=kwargs,
            result=result,
            execution_time_ms=latency_ms,
        )


diagnostic_tool_registry = DiagnosticToolRegistry()

