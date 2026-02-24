#  os_automation/tests/agents_testing.py 

import pyautogui
import tempfile
import os
from pathlib import Path
from os_automation.core.orchestrator import Orchestrator 

# -----------------------------
# 🧪 Test Cases
# -----------------------------
TEST_CASES = [
    # 📁 File System
    "Go to file explorer and Open Documents folder",
    "Create text.txt on Documents folder",
    "Take a screenshot of current screen and save it as imageTest.png on Documents folder",

    # 🌐 Browser
    "Open Youtube in browser and play random music",
    "Open gmail in browser and check for new mail",
    "Search Python tutorial in Browser and click first link",
    "Open gmail in browser, Click on compose to write new mail, write 'your-mail-address' in TO field, 'Test Automation' in subject field and 'This is a test' in body then send the mail",

    # 📝 Text Editor
    "Open text editor in system and type 'Meeting at 5' and save it using CTRL+S on Documents/Vedanshi folder as TestingNote.txt",

    # ⚙️ System
    "Open system settings and Turn on the Wi-Fi by clicking on toggle button",
    "Open Calculator and do sum of 10 and 500",

    # 💻 VS Code
    "Open new Visual Studio Code window",
    "Open new visual studio code window, create a new file using CTRL+N, type the code \"print('Hello Automation')\" and save it as test.py on Documents folder",
    "Open Documents/test.py file and replace the 'Hello Automation' from print statement by 'Hello OS Automation' and save it using CTRL+S",
    "Open VS Code extension panel using CTRL+SHIFT+X, search for Python extension and install it by clicking on install button",

    # 🌍 FTP Advanced Test
    "Open the terminal. Connect to FTP server ftp.emptyops.com on port 21 using username 'sub@spdev.emptyops.com' and password '6Ij2-xfP]WG4'. Navigate to the remote directory containing readme.txt in temp_for_wbc_final_test_7. Download the file index.php to ~/Downloads/. Wait until the download is complete and then close the terminal."
]

# -----------------------------
# 🚀 Main Runner
# -----------------------------
def main():
    orch = Orchestrator()

    print("\n==============================")
    print("      AVAILABLE TEST CASES      ")
    print("==============================\n") 

    for index, value in enumerate(TEST_CASES, start=1):
        print(f"{index}. {value}")

    try:
        choice = int(input("\nEnter test case number: "))
        command = TEST_CASES[choice - 1]
    except (ValueError, IndexError):
        print("\n❌ Invalid choice. Please enter a valid number.\n")
        return

    # 📸 Dynamic Screenshot Path (OS Independent)
    screenshot_path = Path(tempfile.gettempdir()) / "temp_screenshot.png"
    pyautogui.screenshot(str(screenshot_path))

    print("\n🚀 Running Test Case...\n")

    result = orch.run(
        command,
        image_path=str(screenshot_path)
    )

    print("\n==============================")
    print("           RESULT               ")
    print("==============================\n")
    print(result)
    print("\n✅ Execution Completed.\n")


if __name__ == "__main__":
    main()