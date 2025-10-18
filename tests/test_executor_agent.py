from os_automation.core.registry import registry
from os_automation.repos.omniparser_adapter import OmniParserAdapter
from os_automation.repos.pyautogui_adapter import PyAutoGUIAdapter
from os_automation.agents.executor_agent import ExecutorAgent

def test_detect_and_execute_flow(tmp_image):
    # register safe adapters
    registry.register_adapter("omniparser", OmniParserAdapter)
    registry.register_adapter("pyautogui", PyAutoGUIAdapter)

    agent = ExecutorAgent(default_detection="omniparser", default_executor="pyautogui")
    result = agent.detect_and_execute(tmp_image)
    assert "detection" in result
    assert "execution" in result
    # execution should be a dict with status success (per demo adapter)
    assert result["execution"].get("status") == "success"
