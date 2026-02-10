
import os
import sys
from os_automation.core.orchestrator import Orchestrator

def main():
    """Runs the OS automation orchestrator."""
    # The user query to run
    user_query = "Open browser and go to https://sphereplugins.com/ , go on Products and find Free Plugins and then return the first Plugins name"

    # The orchestrator to run the user query
    orchestrator = Orchestrator(mcp_adapter="mcp_chrome_devtools")
    orchestrator.run(user_query)

if __name__ == '__main__':
    main()
