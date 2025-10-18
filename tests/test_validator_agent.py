from os_automation.agents.validator_agent import ValidatorAgent

def test_validator_combined_pass():
    validator = ValidatorAgent()
    step = {"step_id": 1, "description": "Open terminal"}
    # Execution result mimicking adapter output with detection details
    execution_result = {
        "status": "success",
        "details": {
            "detection": {
                "icon_0": {"label": "terminal", "text": "Terminal", "bbox": [10,10,20,20]}
            }
        }
    }
    report = validator.validate_step(step, execution_result)
    assert report["validation_status"] in ("pass", "fail")  # ensure returned structure
    # In our simple validator, this should be pass
    assert report["validation_status"] == "pass"
