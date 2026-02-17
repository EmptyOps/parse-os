from os_automation.core import orchestrator
from os_automation.core import tal
from os_automation.utils import logger
import time

# Create an instance of the orchestrator
flow = orchestrator.Orchestrator()

# 1. Open YouTube
print("Opening YouTube...")
open_youtube_tal = tal.TAL(
    app="gemini_mcp_chrome_devtools",
    action="navigate_to_url",
    locator="https://www.youtube.com",
    value=None
)
flow.run_automation("Open YouTube", open_youtube_tal)
print("YouTube opened.")

# Give the page some time to load
time.sleep(5)

# 2. Search for "random music"
print("Searching for random music...")
search_tal = tal.TAL(
    app="gemini_mcp_chrome_devtools",
    action="type",
    locator="search input",
    value="random music"
)
flow.run_automation("Search for music", search_tal)
print("Searched for random music.")

# Give the search some time to appear
time.sleep(2)

# 3. Click on the search button
print("Clicking on the search button...")
click_search_tal = tal.TAL(
    app="gemini_mcp_chrome_devtools",
    action="click",
    locator="search button",
    value=None
)
flow.run_automation("Click search button", click_search_tal)
print("Search button clicked.")

# Give the search results time to load
time.sleep(5)

# 4. Click on the first video
print("Clicking on the first video...")
click_video_tal = tal.TAL(
    app="gemini_mcp_chrome_devtools",
    action="click",
    locator="first video in the list",
    value=None
)
flow.run_automation("Click on video", click_video_tal)
print("First video clicked.")

print("Automation finished.")
