from os_automation.core.tal import PlannedStep, ExecutionResult, ValidationReport

def test_planned_step_and_models():
    p = PlannedStep(step_id=1, description="Open terminal")
    assert p.step_id == 1
    er = ExecutionResult(step_id=1, repo_used="pyautogui", decided_event="click", status="success")
    assert er.status == "success"
    vr = ValidationReport(task_id="t1", overall_status="success", validated_steps=[{"step_id": 1}])
    assert vr.overall_status == "success"
