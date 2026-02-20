from os_automation.core import orchestrator

# Create an instance of the orchestrator
flow = orchestrator.Orchestrator(mcp_adapter="gemini_mcp_chrome_devtools")

# The user prompt
prompt = """
Open YouTube in a new browser window.
Search for "random music".
Click the search button.
Click the first video in the search results.
While doing this, identify and record the CSS selectors for the following elements:
- The search input field.
- The search button.
- The link of the first video in the search results.
After the video starts playing, return a JSON object with the identified selectors.
The JSON object should have the following keys: "search_input", "search_button", "first_video_link".
"""

# Run the automation
result = flow.run(prompt)

# Print the result
print(result)
