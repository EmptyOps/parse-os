# os_automation/core/tal.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class PlannedStep(BaseModel):
    step_id: int
    description: str
    metadata: Optional[Dict[str, Any]] = None

class ExecutionResult(BaseModel):
    step_id: int
    repo_used: str
    decided_event: str
    status: str
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

class ValidationReport(BaseModel):
    task_id: str
    overall_status: str
    validated_steps: List[Dict[str, Any]]
