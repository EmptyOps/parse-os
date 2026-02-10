
import os
import sys
from os_automation.core.orchestrator import Orchestrator

def main():
    """Runs the OS automation orchestrator."""
    with open("user_request.txt", "r") as f:
        user_query = f.read()

    # The orchestrator to run the user query
    orchestrator = Orchestrator(mcp_adapter="mcp_chrome_devtools")
    result = orchestrator.run(user_query)
    print(result)

if __name__ == '__main__':
    main()
