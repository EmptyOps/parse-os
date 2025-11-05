from os_automation.core.orchestrator import Orchestrator
from os_automation.core.registry import registry
from os_automation.repos.omniparser_adapter import OmniParserAdapter
from os_automation.repos.pyautogui_adapter import PyAutoGUIAdapter


def test_orchestrator_run(tmp_image):
    # Ensure the orchestrator will have adapters available by registering safe ones
    registry.register_adapter("omniparser", OmniParserAdapter)
    registry.register_adapter("pyautogui", PyAutoGUIAdapter)

    orch = Orchestrator()  # use defaults
    result = orch.run("Open terminal and run ls", image_path=tmp_image)
    # basic structure checks
    assert result.get("user_prompt") == "Open terminal and run ls"
    assert "overall_status" in result
    assert isinstance(result.get("steps"), list)
    # each step should contain execution and validation
    for s in result.get("steps", []):
        assert "execution" in s and "validation" in s
