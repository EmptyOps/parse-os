# os_automation/repos/gemini_mcp_chrome_devtools.py

import subprocess
import json
from os_automation.repos.mcp_base_adapter import MCPBaseAdapter

class GeminiMCPAdapter(MCPBaseAdapter):
    """
    MCP adapter for Gemini CLI / API
    """

    MCP_TYPE = "llm"
    MCP_CAPABILITIES = [
        "reasoning",
        "planning",
        "code generation",
        "analysis",
        "web understanding"
    ]

    def execute(self, payload: dict):
        """
        payload example:
        {
          "task": "Analyze this DOM snapshot and suggest next action",
          "context": {...}
        }
        """

        task = payload.get("task")
        context = payload.get("context", {})

        if not task:
            return {"status": "failed", "error": "missing task"}

        prompt = self._build_prompt(task, context)

        # ---- Option A: Gemini CLI (what you already installed) ----
        proc = subprocess.run(
            ["gemini", "prompt", prompt],
            capture_output=True,
            text=True
        )

        if proc.returncode != 0:
            return {
                "status": "failed",
                "stderr": proc.stderr
            }

        return {
            "status": "success",
            "output": proc.stdout.strip()
        }

    def _build_prompt(self, task: str, context: dict) -> str:
        if not context:
            return task

        return f"""
TASK:
{task}

CONTEXT:
{json.dumps(context, indent=2)}
""".strip()
