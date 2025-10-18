# main_scripts/sikuli_tool_wrapper.py
import time

class ToolWrapper:
    def __init__(self, delay=1):
        self.delay = delay

    def click(self, x, y):
        print(f"[Sikuli] click at ({x},{y})")
        time.sleep(self.delay)

    def type_text(self, x, y, text):
        print(f"[Sikuli] type at ({x},{y}): {text}")
        time.sleep(self.delay)

    def scroll(self, x, y, direction):
        print(f"[Sikuli] scroll at ({x},{y}) direction={direction}")
        time.sleep(self.delay)
