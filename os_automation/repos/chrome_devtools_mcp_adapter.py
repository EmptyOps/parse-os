# # os_automation/repos/chrome_devtools_mcp_adapter.py
# import subprocess
# import time
# import os
# import pychrome
# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


# class ChromeDevToolsMCPAdapter(MCPBaseAdapter):
#     """
#     FULL adapter.
#     Owns browser automation end-to-end using chrome-devtools-mcp.
#     """

#     MCP_CAPABILITIES = [
#         "open browser",
#         "navigate website",
#         "search",
#         "dom interaction",
#         "screenshot",
#         "network inspection"
#     ]

#     def execute(self, payload):
#         """
#         payload example:
#         {
#           "task": "open browser and search for Python Tutorial"
#         }
#         """

#         # --------------------------------------------------
#         # 1. Start Chrome (CDP)
#         # --------------------------------------------------
#         chrome_cmd = [
#             "google-chrome",
#             "--remote-debugging-port=9222",
#             "--remote-allow-origins=*",
#             "--user-data-dir=/tmp/chrome-mcp"
#         ]

#         subprocess.Popen(chrome_cmd)
#         time.sleep(3)

#         # --------------------------------------------------
#         # 2. Start chrome-devtools-mcp
#         # --------------------------------------------------
#         env = os.environ.copy()
#         env["CHROME_REMOTE_DEBUGGING_URL"] = "ws://127.0.0.1:9222"

#         mcp_proc = subprocess.Popen(
#             ["node", "build/src/main.js"],
#             cwd="/home/emptyops/Documents/Vedanshi/MCP_ChromeDevtool/chrome-devtools-mcp",
#             env=env,
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL
#         )

#         time.sleep(2)

#         # --------------------------------------------------
#         # 3. Perform browser task (simple, deterministic)
#         # --------------------------------------------------
#         # NOTE:
#         # chrome-devtools-mcp automatically opens a blank page.
#         # We rely on Chrome default behavior + CDP injection.


#         browser = pychrome.Browser(url="http://127.0.0.1:9222")
#         tab = browser.new_tab()
#         tab.start()
#         tab.Page.navigate(url="https://sphereplugins.com/")
#         tab.wait(2)

#         # Find and click the "Blog" link.
#         root_node = tab.DOM.getDocument()
#         blog_link = tab.DOM.querySelector(nodeId=root_node['root']['nodeId'], selector='a[href="https://sphereplugins.com/blog/"]')
#         if blog_link:
#             box_model = tab.DOM.getBoxModel(nodeId=blog_link['nodeId'])
#             quad = box_model['model']['border']
#             x = (quad[0] + quad[2]) / 2
#             y = (quad[1] + quad[5]) / 2
#             tab.Input.dispatchMouseEvent(type='mousePressed', x=x, y=y, button='left', clickCount=1)
#             tab.Input.dispatchMouseEvent(type='mouseReleased', x=x, y=y, button='left', clickCount=1)

#         tab.wait(5)

#         # Find and click the blog post
#         root_node = tab.DOM.getDocument()
#         post_link = tab.DOM.querySelector(nodeId=root_node['root']['nodeId'], selector='a[href="https://sphereplugins.com/from-website-to-leads-part-2/"]')
#         if post_link:
#             box_model = tab.DOM.getBoxModel(nodeId=post_link['nodeId'])
#             quad = box_model['model']['border']
#             x = (quad[0] + quad[2]) / 2
#             y = (quad[1] + quad[5]) / 2
#             tab.Input.dispatchMouseEvent(type='mousePressed', x=x, y=y, button='left', clickCount=1)
#             tab.Input.dispatchMouseEvent(type='mouseReleased', x=x, y=y, button='left', clickCount=1)

#         tab.wait(5)
        
#         # --------------------------------------------------
#         # 4. Done
#         # --------------------------------------------------
#         return {
#             "status": "success",
#             "message": f"Browser opened and searched for '{search_query}' using Chrome DevTools"
#         }



# os_automation/repos/chrome_devtools_mcp_adapter.py
#
# ── CHANGE FROM ORIGINAL ─────────────────────────────────────────────────────
# Only 2 lines added at the top of execute(). Everything else is identical.
#
# Bug: `search_query` was used in the return statement but never assigned.
# This caused NameError: name 'search_query' is not defined on every call.
# Fix: read task and search_query from payload at the start of execute().
# ─────────────────────────────────────────────────────────────────────────────

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
        # >>> ADDED: extract search_query so the return statement at the
        # >>> bottom does not raise NameError. Falls back to task string.
        task = payload.get("task", "")
        search_query = payload.get("search_query") or task

        chrome_cmd = [
            "google-chrome",
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
            "--user-data-dir=/tmp/chrome-mcp"
        ]

        subprocess.Popen(chrome_cmd)
        time.sleep(3)

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

        browser = pychrome.Browser(url="http://127.0.0.1:9222")
        tab = browser.new_tab()
        tab.start()
        tab.Page.navigate(url="https://sphereplugins.com/")
        tab.wait(2)

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

        return {
            "status": "success",
            "message": f"Browser opened and searched for '{search_query}' using Chrome DevTools"
        }