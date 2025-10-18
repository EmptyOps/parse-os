from os_automation.core.registry import registry
from os_automation.repos.pyautogui_adapter import PyAutoGUIAdapter
from os_automation.agents.executor_agent import ExecutorAgent

class MockMCPAdapter:
    def execute(self, step):
        # pretend the MCP handled the request
        return {"status": "success", "message": "mcp created"}

def test_mcp_first_routing():
    # register python visual fallback adapter
    registry.register_adapter("pyautogui", PyAutoGUIAdapter)
    # register a mock MCP
    registry.register_adapter("mcp_filesystem", MockMCPAdapter)

    agent = ExecutorAgent(default_executor="pyautogui")
    step = {"description": "Create folder reports", "params": {"name": "reports"}}
    out = agent.execute_with_mcp_or_visual(step)
    assert out.get("status") == "success"
    assert "mcp" in out.get("message", "") or out.get("message") == "mcp created"
