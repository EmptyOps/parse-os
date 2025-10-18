# os_automation/repos/sikuli_adapter.py
from os_automation.core.adapters import BaseAdapter
# from main_scripts.sikuli_tool_wrapper import ToolWrapper as SikuliTool
import os
import sys

# Add project root (PARSE_OS) to sys.path dynamically
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from main_scripts.sikuli_tool_wrapper import ToolWrapper as SikuliTool


class SikuliAdapter(BaseAdapter):
    def __init__(self):
        self.tool = SikuliTool()

    def detect(self, step):
        return {"status": "not_applicable"}

    def execute(self, step):
        bbox = step.get("bbox")
        event = step.get("event")
        if not bbox:
            raise ValueError("bbox required")
        x, y, w, h = bbox
        cx = x + w // 2
        cy = y + h // 2
        if event == "click":
            self.tool.click(cx, cy)
        elif event == "type":
            self.tool.type_text(cx, cy, step.get("text", ""))
        elif event == "scroll":
            self.tool.scroll(cx, cy, step.get("direction", "up"))
        return {"status": "success"}

    def validate(self, step):
        return {"validation": "ok"}
