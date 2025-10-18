from os_automation.core.orchestrator import Orchestrator

def test_basic_flow():
    orch = Orchestrator()
    result = orch.run("Open terminal and run ls")
    assert result["overall_status"] == "success"
    assert len(result["steps"]) > 0
