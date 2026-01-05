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
        # "Search Python Tutorial on browser and open first link from result",
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
        # "open Youtube in browser and play random music",
        # "Go to file explorer and Open DeepSeek folder placed inside Documents folder",
        # "Go to file explorer, Open Documents\DeepSeek folder ",
        # "Open Vedanshi named folder",

        
        # "Go to file explorer and Open Documents folder",
        # "Create text.txt on Documents folder",
        # "take a screenshot of current screen and save it as imageTest.png on Documents folder",
        # "open Youtube in browser and play random music",
        # "open gmail in browser and check for new mail",
        # "Open text editor in system and types 'Meeting at 5' and save it using CTRL+S on Documents/Vedanshi folder as TestingNote.txt",
        # "Search Python tutorial in Browser and click first link",
        # "Open setting of the system and Turn on the Wi-FI by click on toggle button of Wi-FI",
        "Open Calculator and do sum of 10 and 500",
        # "open gmail in browser, Click on compose to write new mail, write 'your-mail-address' in to TO field, 'Test Automation' on subject field and 'This is a test' on body part of mail then sent the mail",

        image_path=screenshot_path
    )

    print(result)

if __name__ == "__main__":
    main()
