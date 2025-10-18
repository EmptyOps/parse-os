"""
Small example using orchestrator to run a prompt + image.
Place a sample image at tests/sample.png for a quick test.
"""
from os_automation.core.orchestrator import Orchestrator
import pathlib

if __name__ == "__main__":
    orchestrator = Orchestrator()
    sample = str(pathlib.Path("tests/sample.png").resolve())
    result = orchestrator.run_task("Open terminal and run ls", image_path=sample)
    import json
    print(json.dumps(result, indent=2))
