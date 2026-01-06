# # os_automation/repos/pyautogui_adapter.py
# from os_automation.tools.pyautogui.py_auto_tool import PyAutoTool
# from os_automation.core.adapters import BaseAdapter


# class PyAutoGUIAdapter(BaseAdapter):
#     def __init__(self):
#         self.tool = PyAutoTool()

#     def detect(self, step):
#         return {"status": "not_applicable"}

#     def execute(self, step):
#         bbox = step.get("bbox")
#         event = step.get("event")
#         if not bbox:
#             raise ValueError("bbox required")
#         x, y, w, h = bbox
#         cx = x + w // 2
#         cy = y + h // 2
#         if event == "click":
#             self.tool.click(cx, cy)
#         elif event == "type":
#             self.tool.type_text(cx, cy, step.get("text", ""))
#         elif event == "scroll":
#             self.tool.scroll(cx, cy, step.get("direction", "up"))
#         return {"status": "success"}

#     def validate(self, step):
#         return {"validation": "ok"}



# os_automation/repos/pyautogui_adapter.py
import os
import time
import logging
from typing import Dict, Any, List

import pyautogui

from os_automation.tools.pyautogui.py_auto_tool import PyAutoTool
from os_automation.core.adapters import BaseAdapter

logger = logging.getLogger(__name__)


class PyAutoGUIAdapter(BaseAdapter):
    """
    Adapter wrapping PyAutoTool for: click, type, keypress, hotkey, scroll, screenshot.
    This is the adapter used by ExecutorAgent in the orchestrator.
    """
    
    # 🔐 Explicit capability contract
    SUPPORTED_EVENTS = {
        "click",
        "double_click",
        "type",
        "keypress",
        "hotkey",
        "scroll",
        "right_click",
    }

    def __init__(self):
        self.tool = PyAutoTool()
        self.output_dir = os.path.join(os.getcwd(), "os_automation_output")
        os.makedirs(self.output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # DETECT — not used for PyAutoGUI
    # ---------------------------------------------------------
    def detect(self, step):
        return {"status": "not_applicable"}

    # ---------------------------------------------------------
    # EXECUTE — generic handler used by ExecutorAgent
    # ---------------------------------------------------------
    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        step = {
            "event": "click|type|keypress|hotkey|scroll",
            "bbox": [x,y,w,h],
            "text": "...",
            "key": "...",
            "keys": ["ctrl","a"],
            "direction": "up|down",
            # optionally: "decision": {"event": ..., "text": ..., "key": ...}
        }
        """
        event = step.get("event")
        bbox = step.get("bbox")
        text = step.get("text")
        key = step.get("key")
        keys = step.get("keys")
        direction = step.get("direction")

        # ✅ Backward-compatible: if event is missing but 'decision' is present,
        # pull fields from decision.
        decision = step.get("decision") or {}
        if event is None and decision:
            event = decision.get("event", event)
            text = text or decision.get("text")
            key = key or decision.get("key")
            keys = keys or decision.get("keys")
            direction = direction or decision.get("direction")

        if not bbox:
            raise ValueError("bbox required")

        x, y, w, h = bbox
        cx = x + w // 2
        cy = y + h // 2

        logger.debug(f"[PyAutoGUIAdapter] EXECUTE event={event} at cx={cx}, cy={cy}")

        try:
            if event == "click":
                self.tool.click(cx, cy)

            # elif event == "type":
            #     self.tool.type_text(cx, cy, text or "")
            
            elif event == "type":
                pyautogui.write(text or "", interval=0.03)

            elif event == "keypress":
                # key could be: enter, backspace, delete, left, right, up, down...
                self.tool.keypress(key)

            elif event == "hotkey":
                # keys is list: ["ctrl","v"]
                self.tool.hotkey(keys)

            elif event == "scroll":
                self.tool.scroll(cx, cy, direction)
                
            elif event == "double_click":
                self.tool.doubleClick(cx, cy)
                
            elif event == "right_click":
                self.tool.right_click(cx, cy)

            else:
                raise ValueError(f"Unknown event {event}")

            return {"status": "success"}

        except Exception as e:
            logger.exception("Execution failed: %s", e)
            return {"status": "failed", "error": str(e)}

    # ---------------------------------------------------------
    # VALIDATE — not used here (ValidatorAgent is separate)
    # ---------------------------------------------------------
    def validate(self, step):
        return {"validation": "ok"}

    # ---------------------------------------------------------
    # SCREENSHOT (used by ExecutorAgent)
    # ---------------------------------------------------------
    def screenshot(self, prefix="screen") -> str:
        import pyautogui

        timestamp = int(time.time() * 1000)
        path = os.path.join(self.output_dir, f"{prefix}_{timestamp}.png")
        try:
            img = pyautogui.screenshot()
            img.save(path)
            return path
        except Exception as e:
            logger.exception("Screenshot failed: %s", e)
            return ""