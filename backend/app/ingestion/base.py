from abc import ABC, abstractmethod
from typing import Any, Dict

from app.schemas import IncidentEvent


class AlertParserStrategy(ABC):
    @abstractmethod
    def can_parse(self, payload: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def parse(self, payload: Dict[str, Any]) -> IncidentEvent:
        pass

