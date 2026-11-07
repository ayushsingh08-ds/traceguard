from typing import Any, Dict, List

from app.ingestion.base import AlertParserStrategy
from app.ingestion.cloudwatch import CloudWatchAlertParser
from app.ingestion.custom import CustomAlertParser
from app.ingestion.prometheus import PrometheusAlertParser
from app.schemas import IncidentEvent


class AlertParserRegistry:
    def __init__(self) -> None:
        # Ordered by parsing specificity: vendor-specific payload signatures
        # must be evaluated prior to the generic fallback parser.
        self._strategies: List[AlertParserStrategy] = [
            PrometheusAlertParser(),
            CloudWatchAlertParser(),
            CustomAlertParser(),
        ]

    def register(self, strategy: AlertParserStrategy, priority: int = 0) -> None:
        self._strategies.insert(priority, strategy)

    def resolve_and_parse(self, payload: Dict[str, Any]) -> IncidentEvent:
        for strategy in self._strategies:
            if strategy.can_parse(payload):
                return strategy.parse(payload)
        raise ValueError("No parser strategy capable of processing the given alert payload")


alert_parser_registry = AlertParserRegistry()
