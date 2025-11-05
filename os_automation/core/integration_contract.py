# os_automation/core/integration_contract.py
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class IntegrationMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    HYBRID = "hybrid"


class IntegrationContract(BaseModel):
    repo_name: str
    adapter_class: str
    integration_mode: IntegrationMode = IntegrationMode.PARTIAL
    capabilities: List[str] = ["detect", "execute", "validate"]
    dependencies: Optional[List[str]] = None
    config_options: Optional[Dict[str, Any]] = None
