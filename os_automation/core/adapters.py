# os_automation/core/adapters.py
from abc import ABC, abstractmethod
from typing import Any, Dict

from os_automation.core.integration_contract import IntegrationMode


class BaseAdapter(ABC):
    # New metadata defaults that each adapter can override
    integration_mode: IntegrationMode = IntegrationMode.PARTIAL
    capabilities = ["detect", "execute", "validate"]

    @abstractmethod
    def detect(self, step: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def validate(self, step: Dict[str, Any]) -> Dict[str, Any]:
        pass
