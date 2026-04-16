# os_automation/repos/mcp_base_adapter.py

from os_automation.core.adapters import BaseAdapter
from os_automation.core.integration_contract import IntegrationMode

class MCPBaseAdapter(BaseAdapter):
    """
    Base class for all MCP servers (Chrome, Slack, Filesystem, etc.)
    """

    integration_mode = IntegrationMode.FULL
    capabilities = ["plan", "execute"]

    # Human-readable capability hints for planner
    MCP_CAPABILITIES = []
    MCP_ENDPOINT = None

    def plan(self, user_prompt: str):
        """
        Return structured steps OR a direct execution instruction.
        """
        raise NotImplementedError

    def execute(self, payload):
        """
        Execute via local MCP server (JSON-RPC later).
        """
        raise NotImplementedError

    def detect(self, step):
        raise NotImplementedError("MCP adapters do not use vision")

    def validate(self, step):
        return {"validation_status": "pass"}