import pyautogui
import time
import sys

class ToolWrapper:
    def __init__(self, delay=0.2):
        self.delay = delay
        print("[DEBUG] ✅ PyAutoGUI ToolWrapper initialized and active", flush=True, file=sys.stderr)
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05

    def _move_and_wait(self, x, y):
        """Ensure the cursor actually moves on screen before an action."""
        try:
            pyautogui.moveTo(x, y, duration=0.15)  # Smooth move ensures visibility
            time.sleep(0.05)
        except Exception as e:
            print(f"[ERROR] moveTo failed: {e}", flush=True, file=sys.stderr)

    def click(self, x, y):
        print(f"[DEBUG] 🖱️ click({x}, {y}) called via tool_wrapper.py", flush=True, file=sys.stderr)
        self._move_and_wait(x, y)
        pyautogui.click(x, y)
        time.sleep(self.delay)

    def double_click(self, x, y):
        print(f"[DEBUG] 🖱️ double_click({x}, {y}) called via tool_wrapper.py", flush=True, file=sys.stderr)
        self._move_and_wait(x, y)
        pyautogui.doubleClick(x, y)
        time.sleep(self.delay)

    def right_click(self, x, y):
        print(f"[DEBUG] 🖱️ right_click({x}, {y}) called via tool_wrapper.py", flush=True, file=sys.stderr)
        self._move_and_wait(x, y)
        pyautogui.rightClick(x, y)
        time.sleep(self.delay)

    def type_text(self, x, y, text):
        print(f"[DEBUG] ⌨️ type_text({x}, {y}, '{text}') via tool_wrapper.py", flush=True, file=sys.stderr)
        self._move_and_wait(x, y)
        pyautogui.click(x, y)
        pyautogui.typewrite(text, interval=0.05)

    def scroll(self, x, y, direction):
        print(f"[DEBUG] 🖱️ scroll({x}, {y}, '{direction}') via tool_wrapper.py", flush=True, file=sys.stderr)
        self._move_and_wait(x, y)
        if direction == "up":
            pyautogui.scroll(300)
        elif direction == "down":
            pyautogui.scroll(-300)
        else:
            print(f"[WARN] Unknown scroll direction: {direction}", flush=True, file=sys.stderr)

