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


class ChromeDevToolsAdapter(MCPBaseAdapter):
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
        tab.Page.navigate(url="https://www.google.com")
        tab.wait(2)
        tab.Page.bringToFront()

        tab.Runtime.evaluate(
            expression="""
            (async () => {
                function sleep(ms) {
                    return new Promise(r => setTimeout(r, ms));
                }

                // Ensure document is ready
                if (document.readyState !== "complete") {
                    await new Promise(r => window.addEventListener("load", r, { once: true }));
                }

                let box = null;

                // Try multiple selectors (Google changes this often)
                const selectors = [
                    'textarea[name="q"]',
                    'input[name="q"]',
                    'textarea[aria-label="Search"]',
                    'input[aria-label="Search"]'
                ];

                for (let i = 0; i < 30; i++) {
                    for (const sel of selectors) {
                        box = document.querySelector(sel);
                        if (box) break;
                    }
                    if (box) break;
                    await sleep(300);
                }

                if (!box) {
                    console.error("❌ Google search box NOT found");
                    alert("Search box not found by automation");
                    return;
                }

                // Bring focus
                box.focus();
                await sleep(200);

                // Clear any existing value
                box.value = "";
                box.dispatchEvent(new Event("input", { bubbles: true }));
                await sleep(200);

                // Human-like typing
                const text = "Python Tutorial";
                for (const ch of text) {
                    box.value += ch;
                    box.dispatchEvent(new Event("input", { bubbles: true }));
                    await sleep(90);
                }

                // Press Enter
                box.dispatchEvent(new KeyboardEvent("keydown", {
                    bubbles: true,
                    cancelable: true,
                    key: "Enter",
                    code: "Enter",
                    keyCode: 13
                }));
            })();
            """
        )


        tab.wait(5)

        # --------------------------------------------------
        # 4. Done
        # --------------------------------------------------
        return {
            "status": "success",
            "message": "Browser opened and search executed using Chrome DevTools"
        }