# os_automation/repos/gemini_chrome_devtools_mcp_adapter.py

# import subprocess
# import json
# import subprocess
# import time
# import select
# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter

# class GeminiChromeDevToolsMCPAdapter(MCPBaseAdapter):
#     """
#     MCP adapter for Gemini CLI / API
#     """

#     MCP_TYPE = "llm"
#     MCP_CAPABILITIES = [
#         "reasoning",
#         "planning",
#         "code generation",
#         "analysis",
#         "web understanding"
#     ]

#     # def execute(self, payload: dict):
#     #     """
#     #     payload example:
#     #     {
#     #       "task": "Analyze this DOM snapshot and suggest next action",
#     #       "context": {...}
#     #     }
#     #     """

#     #     task = payload.get("task")
#     #     context = payload.get("context", {})

#     #     if not task:
#     #         return {"status": "failed", "error": "missing task"}

#     #     prompt = self._build_prompt(task, context)

#     #     # ---- Option A: Gemini CLI (what you already installed) ----
#     #     proc = subprocess.run(
#     #         ["gemini", "prompt", prompt],
#     #         capture_output=True,
#     #         text=True
#     #     )

#     #     if proc.returncode != 0:
#     #         return {
#     #             "status": "failed",
#     #             "stderr": proc.stderr
#     #         }

#     #     return {
#     #         "status": "success",
#     #         "output": proc.stdout.strip()
#     #     }

#     def execute(self, payload: dict):
#         task = payload.get("task")
#         if not task:
#             return {"status": "failed", "error": "missing task"}

#         proc = subprocess.Popen(
#             ["gemini"],
#             stdin=subprocess.PIPE,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#             bufsize=1
#         )

#         output_lines = []

#         # Wait for Gemini prompt
#         while True:
#             line = proc.stdout.readline()
#             if not line:
#                 break
#             output_lines.append(line)

#             if line.strip().endswith(">"):
#                 break

#         # Now Gemini is READY — send the task
#         proc.stdin.write(task + "\n")
#         proc.stdin.flush()

#         # Give agent time to work
#         time.sleep(2)

#         # Exit cleanly
#         proc.stdin.write("exit\n")
#         proc.stdin.flush()

#         stdout, stderr = proc.communicate(timeout=180)

#         return {
#             "status": "success",
#             "output": "".join(output_lines) + stdout
#         }


#     def _build_prompt(self, task: str, context: dict) -> str:
#         if not context:
#             return task

#         return f"""
# TASK:
# {task}

# CONTEXT:
# {json.dumps(context, indent=2)}
# """.strip()


# os_automation/repos/gemini_chrome_devtools_mcp_adapter.py
# import os
# import pty
# import select
# import subprocess
# import time

# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


# class GeminiChromeDevToolsMCPAdapter(MCPBaseAdapter):
#     MCP_TYPE = "llm"
#     MCP_CAPABILITIES = [
#         "reasoning",
#         "planning",
#         "analysis",
#         "web_understanding"
#     ]

#     def execute(self, payload: dict):
#         task = payload.get("task")
#         if not task:
#             return {"status": "failed", "error": "missing task"}

#         master_fd, slave_fd = pty.openpty()

#         proc = subprocess.Popen(
#             ["gemini"],
#             stdin=slave_fd,
#             stdout=slave_fd,
#             stderr=slave_fd,
#             close_fds=True
#         )
#         os.close(slave_fd)

#         output = ""

#         def read_until_prompt(timeout=60):
#             """Wait until Gemini shows a command prompt '>'"""
#             nonlocal output
#             start = time.time()
#             while time.time() - start < timeout:
#                 r, _, _ = select.select([master_fd], [], [], 0.1)
#                 if master_fd in r:
#                     data = os.read(master_fd, 4096).decode(errors="ignore")
#                     output += data
#                     if "\n> " in output or output.rstrip().endswith(">"):
#                         return True
#             return False

#         def send(cmd: str, wait=1.5):
#             """Send a command as if typed by a human"""
#             nonlocal output
#             os.write(master_fd, (cmd + "\n").encode())
#             time.sleep(wait)
#             while True:
#                 r, _, _ = select.select([master_fd], [], [], 0.1)
#                 if master_fd in r:
#                     try:
#                         output += os.read(master_fd, 4096).decode(errors="ignore")
#                     except OSError:
#                         break
#                 else:
#                     break

#         # 1️⃣ Wait for Gemini REPL
#         if not read_until_prompt():
#             return {
#                 "status": "failed",
#                 "error": "Gemini prompt not detected",
#                 "output": output
#             }

#         # 2️⃣ (Optional) Ensure IDE companion (safe if already installed)
#         send("/ide install", wait=2)

#         # 3️⃣ (Optional) Verify MCP connectivity
#         send("/mcp", wait=2)

#         # 4️⃣ Send natural language task
#         send(task, wait=6)

#         # 5️⃣ Quit cleanly
#         send("/quit", wait=1)

#         return {
#             "status": "success",
#             "output": output
#         }


import subprocess
from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


class GeminiChromeDevToolsMCPAdapter(MCPBaseAdapter):
    MCP_TYPE = "llm"
    MCP_CAPABILITIES = [
        "reasoning",
        "planning",
        "analysis",
        "web_understanding"
    ]

    def execute(self, payload: dict):
        task = payload.get("task")
        if not task:
            return {"status": "failed", "error": "missing task"}

        try:
            proc = subprocess.run(
                ["./run_gemini_mcp.sh", task],
                text=True,
                capture_output=True,
                timeout=300
            )

            return {
                "status": "success" if proc.returncode == 0 else "failed",
                "output": proc.stdout,
                "error": proc.stderr if proc.returncode else None
            }

        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }