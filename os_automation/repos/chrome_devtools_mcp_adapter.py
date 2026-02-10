# # os_automation/repos/chrome_devtools_mcp_adapter.py

# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter

# class ChromeDevToolsMCPAdapter(MCPBaseAdapter):
#     """
#     Chrome DevTools MCP Server (local install)
#     """

#     MCP_CAPABILITIES = [
#         "open url",
#         "inspect dom",
#         "query selector",
#         "click element",
#         "type in input",
#         "run javascript",
#         "network inspection",
#         "browser automation",
#         "web testing"
#     ]

#     def plan(self, user_prompt: str):
#         """
#         Return a normalized MCP execution intent.
#         """
#         return {
#             "tool": "chrome_devtools",
#             "intent": user_prompt
#         }

#     def execute(self, payload):
#         """
#         Placeholder: real JSON-RPC will be implemented later.
#         """
#         return {
#             "status": "success",
#             "message": "Chrome DevTools MCP would execute this",
#             "payload": payload
#         }

# # os_automation/repos/chrome_devtools_mcp_adapter.py
# import subprocess
# import json
# import time
# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


# class ChromeDevToolsMCPAdapter(MCPBaseAdapter):

#     def __init__(self, **kwargs):
#         self.proc = subprocess.Popen(
#             ["node", "build/src/main.js"],
#             stdin=subprocess.PIPE,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#             bufsize=1
#         )

#         # --- MCP INITIALIZE (MANDATORY) ---
#         init_msg = {
#             "jsonrpc": "2.0",
#             "id": 0,
#             "method": "initialize",
#             "params": {
#                 "clientInfo": {
#                     "name": "parse-os",
#                     "version": "0.1"
#                 }
#             }
#         }

#         self._send(init_msg)
#         self._read()  # read initialize response

#     def _send(self, msg: dict):
#         self.proc.stdin.write(json.dumps(msg) + "\n")
#         self.proc.stdin.flush()

#     def _read(self, timeout=2):
#         """Read one MCP response line"""
#         start = time.time()
#         while time.time() - start < timeout:
#             line = self.proc.stdout.readline()
#             if line:
#                 return line.strip()
#         return None

#     def execute(self, payload):

#         open_msg = {
#             "jsonrpc": "2.0",
#             "id": 1,
#             "method": "browser.open",
#             "params": {
#                 "url": "https://www.google.com"
#             }
#         }

#         self._send(open_msg)

#         reply = self._read(timeout=5)

#         return {
#             "status": "success",
#             "reply": reply
#         }


# os_automation/repos/chrome_devtools_mcp_adapter.py
import subprocess
import time
import os
import pychrome
from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


class ChromeDevToolsMCPAdapter(MCPBaseAdapter):
    """
    FULL adapter.
    Owns browser automation end-to-end using chrome-devtools-mcp.
    """

    MCP_CAPABILITIES = [
        "open browser",
        "navigate website",
        "search",
        "dom interaction",
        "screenshot",
        "network inspection"
    ]

    def execute(self, payload):
        """
        payload example:
        {
          "task": "open browser and search for Python Tutorial"
        }
        """

        # --------------------------------------------------
        # 1. Start Chrome (CDP)
        # --------------------------------------------------
        chrome_cmd = [
            "google-chrome",
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
            "--user-data-dir=/tmp/chrome-mcp"
        ]

        subprocess.Popen(chrome_cmd)
        time.sleep(3)

        # --------------------------------------------------
        # 2. Start chrome-devtools-mcp
        # --------------------------------------------------
        env = os.environ.copy()
        env["CHROME_REMOTE_DEBUGGING_URL"] = "ws://127.0.0.1:9222"

        mcp_proc = subprocess.Popen(
            ["node", "build/src/main.js"],
            cwd="/home/emptyops/Documents/Vedanshi/MCP_ChromeDevtool/chrome-devtools-mcp",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(2)

        # --------------------------------------------------
        # 3. Perform browser task (simple, deterministic)
        # --------------------------------------------------
        # NOTE:
        # chrome-devtools-mcp automatically opens a blank page.
        # We rely on Chrome default behavior + CDP injection.


        browser = pychrome.Browser(url="http://127.0.0.1:9222")
        tab = browser.new_tab()
        tab.start()
        tab.Page.navigate(url="https://sphereplugins.com/")
        tab.wait(2)

        # Find and click the "Blog" link.
        root_node = tab.DOM.getDocument()
        blog_link = tab.DOM.querySelector(nodeId=root_node['root']['nodeId'], selector='a[href="https://sphereplugins.com/blog/"]')
        if blog_link:
            box_model = tab.DOM.getBoxModel(nodeId=blog_link['nodeId'])
            quad = box_model['model']['border']
            x = (quad[0] + quad[2]) / 2
            y = (quad[1] + quad[5]) / 2
            tab.Input.dispatchMouseEvent(type='mousePressed', x=x, y=y, button='left', clickCount=1)
            tab.Input.dispatchMouseEvent(type='mouseReleased', x=x, y=y, button='left', clickCount=1)

        tab.wait(5)

        # Find and click the blog post
        root_node = tab.DOM.getDocument()
        post_link = tab.DOM.querySelector(nodeId=root_node['root']['nodeId'], selector='a[href="https://sphereplugins.com/from-website-to-leads-part-2/"]')
        if post_link:
            box_model = tab.DOM.getBoxModel(nodeId=post_link['nodeId'])
            quad = box_model['model']['border']
            x = (quad[0] + quad[2]) / 2
            y = (quad[1] + quad[5]) / 2
            tab.Input.dispatchMouseEvent(type='mousePressed', x=x, y=y, button='left', clickCount=1)
            tab.Input.dispatchMouseEvent(type='mouseReleased', x=x, y=y, button='left', clickCount=1)

        tab.wait(5)
        
        # --------------------------------------------------
        # 4. Done
        # --------------------------------------------------
        return {
            "status": "success",
            "message": f"Browser opened and searched for '{search_query}' using Chrome DevTools"
        }