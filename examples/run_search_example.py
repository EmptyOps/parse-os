"""
Small example using orchestrator to run a prompt with chrome devtools.
"""
from os_automation.core.orchestrator import Orchestrator

if __name__ == "__main__":
    orchestrator = Orchestrator(mcp_adapter="mcp_chrome_devtools")
    result = orchestrator.run("open browser and search for 'Python Tutorial'")
    import json
    print(json.dumps(result, indent=2))