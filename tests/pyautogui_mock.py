from os_automation.repos.pyautogui_adapter import PyAutoGUIAdapter
adapter = PyAutoGUIAdapter()
adapter.execute({"bbox": [10,10,100,50], "event": "click"})

# ✅ Should print: [PyAutoGUI] click at (60,35)