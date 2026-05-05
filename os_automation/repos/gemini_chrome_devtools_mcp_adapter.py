# # os_automation/repos/gemini_chrome_devtools_mcp_adapter.py

# import subprocess
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

#         try:
#             proc = subprocess.run(
#                 ["./run_gemini_mcp.sh", task],
#                 text=True,
#                 capture_output=True,
#                 timeout=300
#             )

#             return {
#                 "status": "success" if proc.returncode == 0 else "failed",
#                 "output": proc.stdout,
#                 "error": proc.stderr if proc.returncode else None
#             }

#         except Exception as e:
#             return {
#                 "status": "failed",
#                 "error": str(e)
#             }



# # os_automation/repos/gemini_chrome_devtools_mcp_adapter.py
# #
# # CHANGES FROM ORIGINAL (marked <<< CHANGED):
# #
# #   1. Script path reads from GEMINI_MCP_SCRIPT env var instead of
# #      hardcoded "./run_gemini_mcp.sh"
# #      Why: hardcoded relative path only works when parse-os is started
# #           from the exact repo root. Any other working directory silently
# #           fails with "file not found".
# #
# #   2. Timeout reads from GEMINI_MCP_TIMEOUT env var instead of
# #      hardcoded 300
# #      Why: consistency with parse-os-pro's MCPStepService which already
# #           reads this from settings. Both layers now respect the same var.
# #
# #   3. Error response includes returncode for easier debugging
# #
# # THE EXECUTE LOGIC IS IDENTICAL TO THE ORIGINAL.
# # Classic parse-os flow (browser_auto_script_mode=False):
# #   Orchestrator.run() → can_use_mcp() → "gemini_mcp_chrome_devtools"
# #   → this adapter → run_gemini_mcp.sh "plain task string"
# #   → run_gemini_mcp.sh classic branch (unchanged) → Gemini executes full task
# # ─────────────────────────────────────────────────────────────────────────────

# import os
# import subprocess
# from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


# # Read from env so the path works regardless of working directory.        # <<< CHANGED 1
# _GEMINI_SCRIPT  = os.getenv("GEMINI_MCP_SCRIPT",  "./run_gemini_mcp.sh") # <<< CHANGED 1
# _GEMINI_TIMEOUT = int(os.getenv("GEMINI_MCP_TIMEOUT", "600"))             # <<< CHANGED 2


# class GeminiChromeDevToolsMCPAdapter(MCPBaseAdapter):
#     """
#     Classic parse-os adapter for Gemini Chrome DevTools MCP.

#     Used when browser_auto_script_mode=False (standard parse-os flow).
#     Receives the full user task as a single string and delegates entirely
#     to run_gemini_mcp.sh which handles the complete browser automation.

#     In pro mode (browser_auto_script_mode=True) this adapter is NOT used —
#     parse-os-pro's MCPStepService calls run_gemini_mcp.sh directly with a
#     JSON payload file, one step at a time.
#     """

#     MCP_TYPE = "llm"
#     MCP_CAPABILITIES = [
#         "reasoning",
#         "planning",
#         "analysis",
#         "web_understanding",
#     ]

#     def execute(self, payload: dict):
#         task = payload.get("task")
#         if not task:
#             return {"status": "failed", "error": "missing task"}

#         try:
#             proc = subprocess.run(
#                 [_GEMINI_SCRIPT, task],                 # <<< CHANGED 1: was "./run_gemini_mcp.sh"
#                 text=True,
#                 capture_output=True,
#                 timeout=_GEMINI_TIMEOUT,                # <<< CHANGED 2: was 300
#             )

#             return {
#                 "status":     "success" if proc.returncode == 0 else "failed",
#                 "output":     proc.stdout,
#                 "error":      proc.stderr if proc.returncode else None,
#                 "returncode": proc.returncode,          # <<< CHANGED 3: added for debugging
#             }

#         except subprocess.TimeoutExpired:
#             return {
#                 "status": "failed",
#                 "error":  f"gemini script timed out after {_GEMINI_TIMEOUT}s",
#             }

#         except FileNotFoundError:
#             return {
#                 "status": "failed",
#                 "error":  (
#                     f"run_gemini_mcp.sh not found at '{_GEMINI_SCRIPT}'. "
#                     "Set the GEMINI_MCP_SCRIPT environment variable to the "
#                     "absolute path of run_gemini_mcp.sh inside your parse-os clone."
#                 ),
#             }

#         except Exception as e:
#             return {
#                 "status": "failed",
#                 "error":  str(e),
#             }





# os_automation/repos/gemini_chrome_devtools_mcp_adapter.py
#
# Classic-mode adapter for parse-os.
#
# WHEN THIS RUNS:
#   browser_auto_script_mode=False
#     → server.py._run_classic()
#       → Orchestrator.run(user_prompt)              # skip_mcp_routing=False
#         → main_agent.can_use_mcp() == "gemini_mcp_chrome_devtools"
#           → THIS adapter.execute({"task": user_prompt})
#             → run_gemini_mcp.sh "<plain task string>"
#               → script's CLASSIC branch (no JSON, no Chrome lifecycle)
#
# WHEN THIS DOES *NOT* RUN:
#   browser_auto_script_mode=True
#     → server.py._run_pro() forwards via HTTP to parse-os-pro:8000
#       → ProOrchestrator._pro_run() calls super().run(skip_mcp_routing=True, ...)
#       → can_use_mcp() is bypassed entirely
#       → step loop calls MCPStepService directly, which calls
#         run_gemini_mcp.sh <json_path> (the PRO branch)
#
# In other words: this adapter is the classic-mode endpoint. Pro mode never
# touches it. That separation is by design — adapter stays single-purpose,
# branching lives upstream in the orchestrator + server.
#
# CHANGES FROM THE ORIGINAL (still relative to the legacy version):
#   1. GEMINI_MCP_SCRIPT  env var, fallback "./run_gemini_mcp.sh"
#   2. GEMINI_MCP_TIMEOUT env var, fallback 300
#      Bumped fallback to 600 to match memory's documented value and
#      to handle DOM-snapshot-heavy tasks that exceed 300s.            # <<< REFINED 1
#   3. returncode included in response
#   4. error falls back to stdout when stderr is empty                 # <<< REFINED 2
#      (Gemini CLI sometimes writes failure detail to stdout)
#   5. Explicit handling of TimeoutExpired and FileNotFoundError
#      so the orchestrator gets actionable messages, not raw tracebacks.

import os
import subprocess
from os_automation.repos.mcp_base_adapter import MCPBaseAdapter


_GEMINI_SCRIPT  = os.getenv("GEMINI_MCP_SCRIPT",  "./run_gemini_mcp.sh")
_GEMINI_TIMEOUT = int(os.getenv("GEMINI_MCP_TIMEOUT", "600"))            # <<< REFINED 1


class GeminiChromeDevToolsMCPAdapter(MCPBaseAdapter):
    """
    Classic parse-os adapter for Gemini + Chrome DevTools MCP.

    Receives the full user task as a single string and delegates entirely
    to run_gemini_mcp.sh's classic branch. No Chrome lifecycle management,
    no per-step JSON, no selector capture — that path lives in
    parse-os-pro's MCPStepService and is reached via HTTP, not via this class.
    """

    MCP_TYPE = "llm"
    MCP_CAPABILITIES = [
        "reasoning",
        "planning",
        "analysis",
        "web_understanding",
    ]

    def execute(self, payload: dict):
        task = payload.get("task")
        if not task:
            return {"status": "failed", "error": "missing task"}

        try:
            proc = subprocess.run(
                [_GEMINI_SCRIPT, task],
                text=True,
                capture_output=True,
                timeout=_GEMINI_TIMEOUT,
            )

            # Surface stdout when stderr is empty — Gemini CLI / bash
            # `set -e` sometimes route the actual failure detail to stdout.
            err = None
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip() or \
                      f"non-zero exit ({proc.returncode}) with no output"  # <<< REFINED 2

            return {
                "status":     "success" if proc.returncode == 0 else "failed",
                "output":     proc.stdout,
                "error":      err,
                "returncode": proc.returncode,
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "error":  f"gemini script timed out after {_GEMINI_TIMEOUT}s",
            }

        except FileNotFoundError:
            return {
                "status": "failed",
                "error":  (
                    f"run_gemini_mcp.sh not found at '{_GEMINI_SCRIPT}'. "
                    "Set GEMINI_MCP_SCRIPT in your parse-os .env to the "
                    "absolute path of run_gemini_mcp.sh inside your parse-os clone, "
                    f"and ensure it is executable: chmod +x {_GEMINI_SCRIPT}"
                ),
            }

        except PermissionError:
            return {
                "status": "failed",
                "error":  f"run_gemini_mcp.sh is not executable. Run: chmod +x {_GEMINI_SCRIPT}",
            }

        except Exception as e:
            return {
                "status": "failed",
                "error":  str(e),
            }