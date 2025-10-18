# os_automation/repos/mcp_adapter.py
import os
import shutil
from os_automation.core.adapters import BaseAdapter
from os_automation.core.integration_contract import IntegrationMode


class MCPFileSystemAdapter(BaseAdapter):
    
    integration_mode = IntegrationMode.PARTIAL
    capabilities = ["execute", "validate", "file_system"]
    
    """
    Example Modular Capability Provider (MCP) adapter.
    Provides structured OS-level file operations directly,
    skipping GUI automation entirely.
    """

    def __init__(self):
        self.base_path = os.path.expanduser("~/Documents")

    def detect(self, step):
        """No visual detection needed for MCP; we just return context info."""
        return {
            "tool_used": "MCPFileSystem",
            "capability": "file_system",
            "available": True
        }

    def execute(self, step):
        desc = step.get("description", "").lower()
        params = step.get("params", {}) or {}
        name = params.get("name") or "new_item"
        content = params.get("content", "")
        mode = params.get("mode", "w")  # default 'w', can be 'a' for append

        target = os.path.join(self.base_path, name)

        try:
            # Create folder
            if "create folder" in desc or "directory" in desc:
                os.makedirs(target, exist_ok=True)
                return {"status": "success", "message": f"Folder created at {target}", "tool_used": "MCPFileSystem"}

            # Delete folder
            elif "delete folder" in desc:
                if os.path.exists(target) and os.path.isdir(target):
                    shutil.rmtree(target)
                    return {"status": "success", "message": f"Folder deleted at {target}", "tool_used": "MCPFileSystem"}
                else:
                    return {"status": "fail", "message": f"Folder not found: {target}", "tool_used": "MCPFileSystem"}

            # Create file
            elif "create file" in desc:
                with open(target, "w") as f:
                    f.write(content)
                return {"status": "success", "message": f"File created at {target}", "tool_used": "MCPFileSystem"}

            # Append to file
            elif "append to file" in desc:
                with open(target, mode) as f:
                    f.write(content)
                return {"status": "success", "message": f"Content appended to {target}", "tool_used": "MCPFileSystem"}

            # Read file
            elif "read file" in desc:
                if os.path.exists(target) and os.path.isfile(target):
                    with open(target, "r") as f:
                        data = f.read()
                    return {"status": "success", "message": f"File read at {target}", "content": data, "tool_used": "MCPFileSystem"}
                else:
                    return {"status": "fail", "message": f"File not found: {target}", "tool_used": "MCPFileSystem"}

            else:
                return {"status": "skipped", "message": "No supported MCP action found"}

        except Exception as e:
            return {"status": "fail", "message": str(e), "tool_used": "MCPFileSystem"}

    def validate(self, step):
        """Basic validation check."""
        desc = step.get("description", "").lower()
        name = (step.get("params") or {}).get("name")
        target = os.path.join(self.base_path, name) if name else None
        if not target:
            return {"validation_status": "fail", "reason": "No target defined"}
        exists = os.path.exists(target)
        return {"validation_status": "pass" if exists else "fail",
                "reason": f"Target {'exists' if exists else 'missing'} at {target}"}
