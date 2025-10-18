# main_scripts/os_assistance.sikuli/os_assistance.py
import sys
import os
import json
import time
import logging

# ---------------- Logging Setup ----------------
LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# ---------------- Add project root to sys.path ----------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
    LOG.info(f"Added ROOT_DIR to sys.path: {ROOT_DIR}")

# ---------------- Tool Paths ----------------
TOOL_PATHS = {
    "sikuli": os.path.join(ROOT_DIR, "main_scripts", "os_assistance.sikuli"),
    "pyautogui": os.path.join(ROOT_DIR, "main_scripts", "pyAutoGUI")
}

# ---------------- OS Assistance Class ----------------
class OSAssistance:
    def __init__(self, tool_name=None, tool_wrapper=None):
        """
        tool_name: Optional - 'sikuli' or 'pyautogui'
        tool_wrapper: Optional - pre-instantiated adapter
        """
        tool_name = tool_name or os.getenv("OS_ASSIST_TOOL", "pyautogui")
        self.tool_name = tool_name

        if tool_wrapper is None:
            if tool_name not in TOOL_PATHS:
                raise ValueError(f"Unsupported tool '{tool_name}', choose from: {list(TOOL_PATHS.keys())}")
            sys.path.insert(0, os.path.abspath(TOOL_PATHS[tool_name]))
            ToolWrapper = __import__("tool_wrapper", fromlist=["ToolWrapper"]).ToolWrapper
            self.tool = ToolWrapper()
            LOG.info(f"Loaded {tool_name} ToolWrapper dynamically")
        else:
            self.tool = tool_wrapper
            LOG.info(f"Using passed-in ToolWrapper: {tool_name}")

    # def handle_event(self, bbox, event_type, text=None, scroll_dir=None, delay=0):
    #     if not bbox or len(bbox) < 4:
    #         raise ValueError("Invalid bbox provided to handle_event")

    #     x, y, w, h = bbox
    #     center_x = x + w // 2
    #     center_y = y + h // 2

    #     LOG.info(f"[OSAssistance] Event={event_type}, Pos=({center_x},{center_y}), Text={text}, Scroll={scroll_dir}")

    #     if event_type == 'click':
    #         print(f"[DEBUG] 🖱️ click({center_x}, {center_y}) via {self.tool_name}")
    #         self.tool.click(center_x, center_y)
    #         if delay > 0 and scroll_dir:
    #             time.sleep(delay)
    #             self.tool.scroll(center_x, center_y, scroll_dir)

    #     elif event_type == 'type':
    #         if not text:
    #             raise ValueError("Text required for 'type' event.")
    #         self.tool.type_text(center_x, center_y, text)

    #     elif event_type == 'scroll':
    #         if scroll_dir not in ['up', 'down']:
    #             raise ValueError("Scroll direction must be 'up' or 'down'.")
    #         self.tool.scroll(center_x, center_y, scroll_dir)

    #     else:
    #         raise ValueError(f"Unsupported event_type: {event_type}")

    def handle_event(self, bbox, event_type, text=None, scroll_dir=None, delay=0):
        if not bbox or len(bbox) < 4:
            raise ValueError("Invalid bbox provided to handle_event")

        x, y, w, h = bbox
        center_x = x + w // 2
        center_y = y + h // 2

        LOG.info(f"[OSAssistance] Event={event_type}, Pos=({center_x},{center_y}), Text={text}, Scroll={scroll_dir}")

        # ✅ CLICK EVENT
        if event_type == 'click':
            LOG.debug(f"[DEBUG] 🖱️ click({center_x}, {center_y}) via {self.tool_name}")
            self.tool.click(center_x, center_y)
            time.sleep(delay or 0.2)

        # ✅ DOUBLE CLICK EVENT
        elif event_type == 'double_click':
            LOG.debug(f"[DEBUG] 🖱️ double_click({center_x}, {center_y}) via {self.tool_name}")
            if hasattr(self.tool, 'double_click'):
                self.tool.double_click(center_x, center_y)
            else:
                # Fallback manual double click
                self.tool.click(center_x, center_y)
                time.sleep(0.15)
                self.tool.click(center_x, center_y)
            time.sleep(delay or 0.3)

        # ✅ RIGHT CLICK EVENT
        elif event_type == 'right_click':
            LOG.debug(f"[DEBUG] 🖱️ right_click({center_x}, {center_y}) via {self.tool_name}")
            if hasattr(self.tool, 'right_click'):
                self.tool.right_click(center_x, center_y)
            else:
                import pyautogui
                pyautogui.rightClick(center_x, center_y)
            time.sleep(delay or 0.2)

        # ✅ TYPE EVENT
        elif event_type == 'type':
            if not text:
                raise ValueError("Text required for 'type' event.")
            LOG.debug(f"[DEBUG] ⌨️ type_text at ({center_x}, {center_y}): {text}")
            self.tool.type_text(center_x, center_y, text)
            time.sleep(delay or 0.1)

        # ✅ SCROLL EVENT
        elif event_type == 'scroll':
            if scroll_dir not in ['up', 'down']:
                raise ValueError("Scroll direction must be 'up' or 'down'.")
            LOG.debug(f"[DEBUG] 🖱️ scroll({scroll_dir}) at ({center_x}, {center_y})")
            self.tool.scroll(center_x, center_y, scroll_dir)
            time.sleep(delay or 0.2)

        else:
            raise ValueError(f"Unsupported event_type: {event_type}")


# ---------------- CLI Compatibility ----------------
def main():
    if len(sys.argv) < 3:
        print("Usage: python os_assistance.py '<bbox>' <event1> [arg1] ... [--delay seconds] [--tool sikuli|pyautogui]")
        sys.exit(1)

    bbox_str = sys.argv[1]
    try:
        bbox = json.loads(bbox_str)
    except Exception as e:
        print("Error parsing bbox JSON:", e)
        sys.exit(1)

    events_args = sys.argv[2:]
    delay_seconds = 0
    tool_name = "pyautogui"

    # Parse optional flags
    if '--delay' in events_args:
        idx = events_args.index('--delay')
        delay_seconds = int(events_args[idx + 1])
        events_args = events_args[:idx] + events_args[idx + 2:]

    if '--tool' in events_args:
        idx = events_args.index('--tool')
        tool_name = events_args[idx + 1]
        events_args = events_args[:idx] + events_args[idx + 2:]

    # ---------------- Load Wrappers ----------------
    try:
        from main_scripts.pyAutoGUI.tool_wrapper import ToolWrapper as PyAutoTool
    except ImportError:
        PyAutoTool = None

    try:
        from main_scripts.sikuli_tool_wrapper import ToolWrapper as SikuliTool
    except ImportError:
        SikuliTool = None

    if tool_name == "pyautogui":
        if not PyAutoTool:
            raise ImportError("PyAutoGUI wrapper not found!")
        tool_wrapper = PyAutoTool()
    else:
        if not SikuliTool:
            raise ImportError("Sikuli wrapper not found!")
        tool_wrapper = SikuliTool()

    assistant = OSAssistance(tool_name=tool_name, tool_wrapper=tool_wrapper)

    # ---------------- Process Events ----------------
    i = 0
    while i < len(events_args):
        event = events_args[i]
        arg = None
        if event in ['type', 'scroll']:
            if i + 1 >= len(events_args):
                print(f"Missing argument for event '{event}'")
                sys.exit(1)
            arg = events_args[i + 1]
            i += 2
        else:
            i += 1

        assistant.handle_event(
            bbox,
            event,
            text=arg if event == 'type' else None,
            scroll_dir=arg if event == 'scroll' else None,
            delay=delay_seconds
        )

        if delay_seconds > 0 and i < len(events_args):
            time.sleep(delay_seconds)


if __name__ == '__main__':
    main()
