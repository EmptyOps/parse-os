# # os_automation/tools/tool_wrapper.sikuli/sikuli_tool.py
import time

# ---------------- Optional SikuliX bridge ----------------
try:
    import org.sikuli.script.Button as Button
    import org.sikuli.script.Key as Key
    import org.sikuli.script.Location as Location
    import org.sikuli.script.Screen as Screen
    _SIKULI_AVAILABLE = True
except ImportError:
    Button = Key = Location = Screen = None
    _SIKULI_AVAILABLE = False
    print("[WARN] Sikuli not available — org.sikuli.script import failed (running without Java bridge).")


class SikuliTool:
    def __init__(self, delay=5):
        """
        SikuliTool wrapper for GUI automation.
        Uses SikuliX (Java bridge). If Sikuli isn't available, raises at runtime.
        """
        self.delay = delay

        if not _SIKULI_AVAILABLE:
            raise RuntimeError(
                "SikuliX is not available in this environment. "
                "Install and run using Jython or SikuliX to enable this tool."
            )

        self.screen = Screen()

    def click(self, x, y):
        """Perform a click at (x, y) using SikuliX."""
        self.screen.click(Location(x, y))
        time.sleep(self.delay)

    def type_text(self, x, y, text):
        """Type text at (x, y)."""
        self.screen.click(Location(x, y))
        self.screen.type(text)

    def scroll(self, x, y, direction):
        """Scroll at (x, y) up or down."""
        self.screen.hover(Location(x, y))
        if direction == "up":
            self.screen.wheel(Location(x, y), Button.WHEEL_UP, 10)
        elif direction == "down":
            self.screen.wheel(Location(x, y), Button.WHEEL_DOWN, 10)
