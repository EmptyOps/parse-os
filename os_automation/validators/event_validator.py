# os_automation/validators/event_validator.py
class EventValidator:
    def validate(self, step, execution_result):
        status = execution_result.get("status") if isinstance(execution_result, dict) else None
        if status != "success":
            return {"validation_status": "fail", "reason": "executor reported failure"}
        return {"validation_status": "pass", "reason": "executor success"}
