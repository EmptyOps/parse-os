# os_automation/repos/pyautogui_adapter.py
from os_automation.tools.pyautogui.py_auto_tool import PyAutoTool
from os_automation.core.adapters import BaseAdapter


class PyAutoGUIAdapter(BaseAdapter):
    def __init__(self):
        self.tool = PyAutoTool()

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
