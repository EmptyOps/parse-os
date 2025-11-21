# from os_automation.core.orchestrator import Orchestrator


# orch = Orchestrator(detection_name="osatlas", executor_name="pyautogui")
# result = orch.run("Open the browser, go to google.com, type 'open source automation' into search and press Enter", image_path="/path/to/screenshot.png")
# print(result)

# tests/agents_testing.py
import pyautogui
from os_automation.core.orchestrator import Orchestrator

def main():
    orch = Orchestrator()

    # 1️⃣ Capture screenshot on the fly
    screenshot_path = "/home/emptyops/Documents/Vedanshi/parse_os/temp_screenshot.png"
    pyautogui.screenshot(screenshot_path)

    # 2️⃣ Pass screenshot to OSAtlas + main agent
    result = orch.run(
        "Open the browser, go to search bar and Search for 'open source automation' into Google and press Enter",
        #"Click on 'File' menu in VS Code bbox and scroll up",
        # "Open Terminal and list out the files",

        image_path=screenshot_path
    )

    print(result)

if __name__ == "__main__":
    main()
