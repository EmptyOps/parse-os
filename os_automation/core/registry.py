# os_automation/core/registry.py
from typing import Any, Dict, Optional

from os_automation.core.integration_contract import (IntegrationContract,
                                                     IntegrationMode)


class Registry:
    def __init__(self):
        self._adapters: Dict[str, Any] = {}
        self._contracts: Dict[str, IntegrationContract] = {}
        self._agents: Dict[str, Any] = {}

    def register_adapter(self, name: str, obj: Any):
        """
        obj may be an adapter class or an adapter factory/instance.
        We store the object and auto-generate a contract from its metadata.
        """
        self._adapters[name] = obj

        # resolve class (if instance, use its class)
        adapter_cls = obj if isinstance(obj, type) else obj.__class__

        # Read metadata with safe defaults
        integration_mode = getattr(adapter_cls, "integration_mode", IntegrationMode.PARTIAL)
        capabilities = getattr(adapter_cls, "capabilities", ["detect", "execute", "validate"])

        contract = IntegrationContract(
            repo_name=name,
            adapter_class=f"{adapter_cls.__module__}.{adapter_cls.__name__}",
            integration_mode=integration_mode,
            capabilities=capabilities
        )
        self._contracts[name] = contract

    def get_adapter(self, name: str) -> Optional[Any]:
        return self._adapters.get(name)

    def get_contract(self, name: str) -> Optional[IntegrationContract]:
        return self._contracts.get(name)

    def list_adapters(self):
        return list(self._adapters.keys())

    def list_contracts(self):
        return {k: v.dict() for k, v in self._contracts.items()}

    def register_agent(self, name: str, obj: Any):
        self._agents[name] = obj

    def get_agent(self, name: str):
        return self._agents.get(name)


# global registry instance
registry = Registry()
