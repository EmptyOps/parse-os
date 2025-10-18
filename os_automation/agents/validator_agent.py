# os_automation/agents/validator_agent.py
from typing import Dict
from os_automation.validators.bbox_validator import BoundingBoxValidator
from os_automation.validators.event_validator import EventValidator

class ValidatorAgent:
    def __init__(self):
        self.bbox_validator = BoundingBoxValidator()
        self.event_validator = EventValidator()

    def validate_step(self, step: Dict, execution_result: Dict) -> Dict:
        bbox_res = self.bbox_validator.validate(step, execution_result)
        event_res = self.event_validator.validate(step, execution_result)
        final_status = "pass" if bbox_res.get("validation_status") == "pass" and event_res.get("validation_status") == "pass" else "fail"
        return {
            "step_id": step.get("step_id"),
            "validation_status": final_status,
            "details": [bbox_res, event_res]
        }
