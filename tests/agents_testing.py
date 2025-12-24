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
        # "Open the browser, go to search bar and Search for 'open source automation' into Google and press Enter",
        # "Click on 'File' menu in VS Code bbox and scroll up",
        # "Open Terminal and list out the files",
        # "Open browser and search Python tutorial",
        # "Search youtube in browser and click on first link",
        # "Search youtube in browser and click on Youtube icone",
        # "Open file explorer and go to Documents Folder",
        # "Open new visual studio code window", 
        # "Open new visual studio code window and create python script name hello.py",
        # "Click on 'file' menu in VS code",
        # "Click on 'Edit' menu in VS code",
        # "Create python.py script on Documents folder",
        # "take a screenshot of current screen and save it as imageTest.png on Documents folder",
        # "Open Documents/Vedanshi folder in the file explorer",
        # "Open system Calculator and do sum of 10 and 500",
        "open Youtube in browser and play random music",

        image_path=screenshot_path
    )

    print(result)

if __name__ == "__main__":
    main()
