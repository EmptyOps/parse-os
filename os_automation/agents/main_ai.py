# # os_automation/agents/main_ai.py
# """
# Main planner agent (YAML in / YAML out).

# - plan(user_prompt: str) -> str  : returns YAML with top-level 'steps' (list of dicts)
# - replan_on_failure(original_prompt, failed_step_yaml, failure_details_yaml) -> str
#     : returns YAML with either revised 'steps' or an 'escalation' object.

# This file merges features from the newer and older variants:
# - OpenAI (chat completion) planner (if OPENAI_API_KEY set)
# - Optional LOCAL LLM POST endpoint
# - Robust YAML extraction & validation
# - Deterministic micro-step fallback
# """
# from __future__ import annotations

# import os
# import re
# import yaml
# import logging
# from typing import Optional, List, Dict, Any

# logger = logging.getLogger(__name__)
# OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

# # If you have a localhost LLM endpoint (text-in/text-out), set it here.
# # If not using, leave as None.
# LOCAL_LLM_URL: Optional[str] = None


# # -----------------------------
# # Utilities: extractors
# # -----------------------------
# def extract_url(prompt: str) -> Optional[str]:
#     """Find first URL or domain-like token in prompt."""
#     m = re.search(r"(https?://[^\s'\"<>]+|[\w\-]+\.[a-zA-Z]{2,})", prompt)
#     return m.group(1) if m else None


# def extract_quoted_text(prompt: str) -> Optional[str]:
#     """Find first quoted phrase (single or double quotes)."""
#     m = re.search(r"'([^']+)'|\"([^\"]+)\"", prompt)
#     if m:
#         return m.group(1) if m.group(1) else m.group(2)
#     return None


# def extract_yaml_from_text(text: str) -> Optional[str]:
#     """
#     Attempt to extract YAML block that contains a top-level 'steps:' or 'escalation:' key.
#     Looks inside fenced code blocks, otherwise searches for 'steps:' index to end.
#     Returns YAML string or None.
#     """
#     if not text:
#         return None

#     # If fenced code blocks exist, check each for a steps: or escalation:
#     if "```" in text:
#         blocks = text.split("```")
#         for b in blocks:
#             if re.search(r"^\s*(steps|escalation)\s*:", b, re.MULTILINE):
#                 return b.strip()

#     # Otherwise find first "steps:" or "escalation:" and return from there to the end.
#     m = re.search(r"(steps|escalation)\s*:", text)
#     if m:
#         idx = m.start()
#         return text[idx:].strip()

#     return None


# def validate_steps_obj(obj: Any) -> bool:
#     """
#     Validate that obj is a dict with 'steps' key and that each step is dict with
#     integer step_id and string description.
#     """
#     try:
#         if not isinstance(obj, dict) or "steps" not in obj:
#             return False
#         steps = obj["steps"]
#         if not isinstance(steps, list) or len(steps) == 0:
#             return False
#         for s in steps:
#             if not isinstance(s, dict):
#                 return False
#             if "step_id" not in s or "description" not in s:
#                 return False
#             # step_id must be int-like
#             sid = s["step_id"]
#             if not isinstance(sid, int):
#                 # allow numeric strings convertible to int
#                 try:
#                     int(sid)
#                 except Exception:
#                     return False
#             if not isinstance(s["description"], str):
#                 return False
#         return True
#     except Exception:
#         return False


# # -----------------------------
# # Main agent
# # -----------------------------
# class MainAIAgent:
#     """
#     Planner agent — YAML IN/OUT.

#     plan(user_prompt: str) -> str  # YAML text with top-level 'steps'
#     replan_on_failure(...) -> str  # YAML text with either revised 'steps' or 'escalation'
#     """

#     def __init__(self, planner_model: str = "gpt-4"):
#         self.planner_model = planner_model

#     # -------------------------
#     # LLM calls
#     # -------------------------
#     def _call_openai(self, prompt: str, max_tokens: int = 600) -> Optional[str]:
#         if not OPENAI_KEY:
#             return None
#         try:
#             import openai
#             openai.api_key = OPENAI_KEY

#             # Use ChatCompletion for backward compatibility
#             resp = openai.ChatCompletion.create(
#                 model=self.planner_model,
#                 messages=[{"role": "user", "content": prompt}],
#                 max_tokens=max_tokens,
#                 temperature=0.0,
#             )
#             content = resp.choices[0].message.content
#             return content
#         except Exception as e:
#             logger.debug("OpenAI call failed: %s", e, exc_info=True)
#             return None

#     def _call_local(self, prompt: str, timeout: int = 10) -> Optional[str]:
#         if not LOCAL_LLM_URL:
#             return None
#         try:
#             import requests
#             r = requests.post(LOCAL_LLM_URL, json={"prompt": prompt}, timeout=timeout)
#             r.raise_for_status()
#             data = r.json()
#             # Expect either {"text": "..."} or {"response": "..."} or raw string
#             text = None
#             if isinstance(data, dict):
#                 text = data.get("text") or data.get("response") or data.get("result")
#             if not text:
#                 # fallback: if server returned a single string
#                 if isinstance(data, str):
#                     text = data
#             return text
#         except Exception as e:
#             logger.debug("Local LLM call failed: %s", e, exc_info=True)
#             return None

#     # -------------------------
#     # Deterministic micro-fallback
#     # -------------------------
#         # -------------------------
#     # Deterministic micro-fallback
#     # -------------------------
#     def _micro_fallback(self, user_prompt: str) -> List[Dict[str, Any]]:
#         """
#         Deterministic fallback that respects the Planner Agent rules:

#         - Output is a list of steps, each with:
#             step_id: int
#             description: string (one atomic UI action)
#         - No login steps.
#         - No 'open browser' unless the USER explicitly requested opening Chrome/browser.
#         - Steps should be executable by the ExecutorAgent.
#         """
#         steps: List[Dict[str, Any]] = []
#         sid = 1
#         low = (user_prompt or "").lower()

#         # -------------------------------
#         # 1) TERMINAL / SHELL INTENT
#         # -------------------------------
#         terminal_keywords = [
#             "terminal", "open terminal", "shell", "bash", "zsh",
#             "run command", "execute", "ls", "pwd", "cat", "mkdir",
#             "list out the files", "list files", "list directory"
#         ]
#         if any(k in low for k in terminal_keywords):
#             # Step 1: open the terminal
#             steps.append({"step_id": sid, "description": "open terminal"})
#             sid += 1

#             quoted = extract_quoted_text(user_prompt)

#             # If user explicitly mentions listing files / directory
#             if "list out the files" in low or "list files" in low or "list directory" in low:
#                 steps.append({"step_id": sid, "description": "run command 'ls -la'"})
#                 sid += 1
#                 return steps

#             # If a command is provided in quotes
#             if quoted:
#                 steps.append({"step_id": sid, "description": f"run command '{quoted}'"})
#                 sid += 1
#                 return steps

#             # Try to extract command after "run" or "execute"
#             m = re.search(r"(?:run|execute)\s+`?\"?([^`'\"]+)`?\"?", user_prompt, re.IGNORECASE)
#             if m:
#                 cmd = m.group(1).strip()
#                 steps.append({"step_id": sid, "description": f"run command '{cmd}'"})
#                 sid += 1
#                 return steps

#             # Fallback: just open terminal and wait for user
#             steps.append({"step_id": sid, "description": "wait for command"})
#             return steps

#         # -------------------------------
#         # 2) BROWSER / SEARCH INTENT
#         # -------------------------------
#         search_keywords = [
#             "google", "search", "internet", "website", "browse",
#             "look up", "search for", "find on google"
#         ]
#         browser_open_intent = any(
#             kw in low for kw in ["open browser", "open chrome", "open google chrome"]
#         )

#         if any(k in low for k in search_keywords) or browser_open_intent:
#             # 🔹 Important: According to your Planner template,
#             # we assume Chrome is already open for generic web tasks.
#             # So we only add "open browser" if the *user explicitly asked* to open it.
#             if browser_open_intent:
#                 steps.append({"step_id": sid, "description": "open browser"})
#                 sid += 1

#             quoted = extract_quoted_text(user_prompt)
#             if quoted:
#                 steps.append({"step_id": sid, "description": "click search box"})
#                 sid += 1
#                 steps.append({"step_id": sid, "description": f"type '{quoted}'"})
#                 sid += 1
#                 steps.append({"step_id": sid, "description": "press enter"})
#                 sid += 1
#                 return steps

#         # -------------------------------
#         # 3) RAW QUOTED INPUT (UNKNOWN CONTEXT)
#         #    – Safe default: treat as typing into a search/input box
#         # -------------------------------
#         quoted = extract_quoted_text(user_prompt)
#         if quoted:
#             steps.append({"step_id": sid, "description": "click search box"})
#             sid += 1
#             steps.append({"step_id": sid, "description": f"type '{quoted}'"})
#             sid += 1
#             steps.append({"step_id": sid, "description": "press enter"})
#             sid += 1
#             return steps

#         # -------------------------------
#         # 4) URL NAVIGATION
#         # -------------------------------
#         url = extract_url(user_prompt)
#         if url:
#             # Only open browser if explicitly requested (otherwise assume it is already open)
#             if browser_open_intent:
#                 steps.append({"step_id": sid, "description": "open browser"})
#                 sid += 1
#             steps.append({"step_id": sid, "description": "click address bar"})
#             sid += 1
#             steps.append({"step_id": sid, "description": f"type '{url}'"})
#             sid += 1
#             steps.append({"step_id": sid, "description": "press enter"})
#             sid += 1
#             return steps

#         # -------------------------------
#         # 5) FALLBACK: Treat instruction as *one* atomic UI step
#         # -------------------------------
#         steps.append({"step_id": sid, "description": user_prompt})
#         return steps


#     # -------------------------
#     # Improved High-Level Planner (YAML out)
#     # -------------------------
#     def plan(self, user_input: str) -> str:
#         """
#         Improved planner:
#         - Outputs high-level steps ONLY
#         - No micro-steps (no clicking, no typing, no press enter)
#         - Executor will break the high-level steps into micro-actions internally
#         """

#         prompt = f"""
# You are an OS task planner.

# Your job: Convert the USER REQUEST into 3–8 HIGH-LEVEL OS TASKS.
# Do NOT output micro steps like:
# - click button
# - type text
# - press enter
# - click search bar
# - click icon

# Instead output ABSTRACT actions such as:
# - open browser
# - navigate to google.com
# - search for "Apple stock price"
# - read the price
# - open the downloads folder
# - open the settings page
# - find a file named "invoice.pdf"

# Rules:
# - The output MUST be YAML.
# - Top-level key MUST be "steps".
# - Each step:
#     - step_id: <integer OR short string>
#     - description: <high-level description>

# User request:
# {user_input}

# Example format:
# steps:
#   - step_id: open_browser
#     description: open Chrome browser
#   - step_id: search
#     description: search for "pyautogui screenshot example"

# Return ONLY YAML.
# """

#         # Try OpenAI if available
#         text = self._call_openai(prompt)

#         # Try local LLM
#         if not text:
#             text = self._call_local(prompt)

#         # Try to parse YAML
#         if text:
#             yaml_candidate = extract_yaml_from_text(text)
#             if yaml_candidate:
#                 try:
#                     parsed = yaml.safe_load(yaml_candidate)
#                     if isinstance(parsed, dict) and "steps" in parsed:
#                         return yaml.safe_dump({"steps": parsed["steps"]}, sort_keys=False)
#                 except Exception:
#                     pass

#         # If LLM fails → fallback to ONE high-level step
#         return yaml.safe_dump({
#             "steps": [
#                 {"step_id": 1, "description": user_input}
#             ]
#         }, sort_keys=False)



#     # -------------------------
#     # Replan on failure / escalation
#     # -------------------------
#     def replan_on_failure(self, original_prompt: str, failed_step_yaml: str, failure_details_yaml: str) -> str:
#         """
#         Called when a step failed repeatedly. Attempt to use LLM to propose:
#           - a revised 'steps' YAML, OR
#           - an 'escalation' block with reason/diagnostics/suggested_manual_steps
#         If LLM fails, return deterministic escalation YAML.
#         """
#         system_msg = (
#             "You are an automation planner. A previous execution failed repeatedly.\n"
#             "Given the original user prompt, the failed step (as YAML), and failure details (as YAML), either produce:\n"
#             "1) a revised YAML plan under 'steps', or\n"
#             "2) an 'escalation' object with fields: reason, diagnostics, suggested_manual_steps.\n\n"
#             "Return only YAML."
#         )

#         user_msg = (
#             f"Original prompt:\n'''{original_prompt}'''\n\n"
#             f"Failed step (YAML):\n{failed_step_yaml}\n\n"
#             f"Failure details (YAML):\n{failure_details_yaml}\n\n"
#             "Return only YAML. Make the escalation actionable (specific selectors/observations if possible)."
#         )

#         combined_prompt = f"{system_msg}\n\n{user_msg}"

#         # Try OpenAI
#         text: Optional[str] = None
#         text = self._call_openai(combined_prompt, max_tokens=800)

#         # Try local
#         if not text:
#             text = self._call_local(combined_prompt)

#         if text:
#             candidate = extract_yaml_from_text(text)
#             if candidate:
#                 try:
#                     parsed = yaml.safe_load(candidate)
#                     # accept either validated 'steps' or an 'escalation' dict
#                     if isinstance(parsed, dict) and ("steps" in parsed or "escalation" in parsed):
#                         # If 'steps' present and valid, return it canonicalized
#                         if "steps" in parsed and validate_steps_obj(parsed):
#                             yaml_text = yaml.safe_dump({"steps": parsed["steps"]}, sort_keys=False)
#                             return yaml_text
#                         # If escalation present, return canonicalized escalation
#                         if "escalation" in parsed:
#                             yaml_text = yaml.safe_dump({"escalation": parsed["escalation"]}, sort_keys=False)
#                             return yaml_text
#                         # If steps present but not strictly valid - still return it (best-effort)
#                         if "steps" in parsed:
#                             yaml_text = yaml.safe_dump({"steps": parsed.get("steps")}, sort_keys=False)
#                             return yaml_text
#                 except Exception as e:
#                     logger.debug("Failed to parse replan LLM YAML candidate: %s", e, exc_info=True)
#             else:
#                 logger.debug("Replan LLM output had no YAML candidate.")

#         # Deterministic escalation fallback
#         logger.debug("Replan falling back to deterministic escalation.")
#         try:
#             failed_step = None
#             failure_details = None
#             try:
#                 failed_step = yaml.safe_load(failed_step_yaml)
#             except Exception:
#                 failed_step = {"raw": failed_step_yaml}

#             try:
#                 failure_details = yaml.safe_load(failure_details_yaml)
#             except Exception:
#                 failure_details = {"raw": failure_details_yaml}

#             escalation = {
#                 "escalation": {
#                     "reason": "step_failed_4_times",
#                     "original_prompt": original_prompt,
#                     "failed_step": failed_step,
#                     "failure_details": failure_details,
#                     "suggested_manual_steps": [
#                         "Manually inspect the 'before' and 'after' screenshots referenced in failure_details.",
#                         "Check if the UI text/labels/selectors have changed since the plan was authored.",
#                         "If necessary, re-run the planner with an explicit instruction such as: "
#                         "'Click the button labeled \"Continue\" in the top-right corner of the page.'"
#                     ]
#                 }
#             }
#             return yaml.safe_dump(escalation, sort_keys=False)
#         except Exception as e:
#             logger.exception("Failed to build deterministic escalation: %s", e)
#             # return a minimal escalation YAML
#             return yaml.safe_dump({
#                 "escalation": {
#                     "reason": "unknown_error",
#                     "original_prompt": original_prompt,
#                     "message": "Unable to generate escalation details programmatically."
#                 }
#             }, sort_keys=False)

    
#     # -------------------------
#     # ActionAgent (YAML in / YAML out) — placed inside MainAIAgent for single-agent constraint
#     # -------------------------
#     def action_for_yaml(self, yaml_request: str) -> str:
#         """
#         YAML in:
#           action_request:
#             description: "click the Save button"
#             screenshot: "/path/to/shot.png"

#         YAML out:
#           action:
#             type: "query_click" | "click_at" | "type" | "run_command" | "open_terminal" | ...
#             query: "Save button"        # for query_click
#             coords: [x, y]              # for click_at
#             bbox: [x,y,w,h]             # optionally
#             text: "hello"               # for type
#             command: "ls -la"           # for run_command
#             key: "enter"                # for keypress
#             meta: {...}
#         """
#         try:
#             req = yaml.safe_load(yaml_request) or {}
#         except Exception:
#             # return a safe default YAML action
#             return yaml.safe_dump({"action": {"type": "query_click", "query": yaml_request}}, sort_keys=False)

#         ar = req.get("action_request", {})
#         desc = (ar.get("description") or "").strip()
#         shot = ar.get("screenshot")

#         # Try LLM function-calling if configured
#         if OPENAI_KEY:
#             try:
#                 import openai, json
#                 openai.api_key = OPENAI_KEY

#                 functions = [
#                     {
#                         "name": "produce_action",
#                         "description": "Produce a structured YAML action for UI automation",
#                         "parameters": {
#                             "type": "object",
#                             "properties": {
#                                 "type": {"type": "string"},
#                                 "query": {"type": "string"},
#                                 "text": {"type": "string"},
#                                 "command": {"type": "string"},
#                                 "coords": {"type": "array", "items": {"type": "integer"}},
#                                 "bbox": {"type": "array", "items": {"type": "integer"}},
#                                 "key": {"type": "string"},
#                                 "meta": {"type": "object"}
#                             },
#                             "required": ["type"]
#                         }
#                     }
#                 ]

#                 messages = [
#                     {"role": "system", "content": "Translate a single atomic UI instruction to a structured action. Return a single function call 'produce_action' with JSON arguments only."},
#                     {"role": "user", "content": desc}
#                 ]

#                 resp = openai.ChatCompletion.create(
#                     model=self.planner_model,
#                     messages=messages,
#                     functions=functions,
#                     function_call={"name": "produce_action"},
#                     temperature=0.0,
#                 )

#                 func_call = resp.choices[0].message.get("function_call")
#                 if func_call and func_call.get("arguments"):
#                     args_text = func_call.get("arguments")
#                     try:
#                         parsed = json.loads(args_text)
#                         return yaml.safe_dump({"action": parsed}, sort_keys=False)
#                     except Exception:
#                         logger.debug("ActionAgent: couldn't parse function args, falling back to rules.")
#             except Exception as e:
#                 logger.debug("ActionAgent LLM call failed: %s", e, exc_info=True)

#         # Deterministic fallback (rules)
#         # Common patterns:
#         m_type = re.search(r"type\s+['\"]([^'\"]+)['\"]", desc)
#         if m_type:
#             action = {"type": "type", "text": m_type.group(1)}
#             return yaml.safe_dump({"action": action}, sort_keys=False)

#         m_clickat = re.search(r"click\s+at\s+(\d+)[,\s]+(\d+)", desc, re.IGNORECASE)
#         if m_clickat:
#             action = {"type": "click_at", "coords": [int(m_clickat.group(1)), int(m_clickat.group(2))]}
#             return yaml.safe_dump({"action": action}, sort_keys=False)

#         if "terminal" in desc.lower() and "run command" not in desc.lower():
#             return yaml.safe_dump({"action": {"type": "open_terminal"}}, sort_keys=False)


#         if "open browser" in desc.lower() or "chrome" in desc.lower() or "firefox" in desc.lower():
#             return yaml.safe_dump({"action": {"type": "open_browser"}}, sort_keys=False)

#         m_run = re.search(r"run\s+command\s+['\"]([^'\"]+)['\"]", desc, re.IGNORECASE)
#         if m_run:
#             return yaml.safe_dump({"action": {"type": "run_command", "command": m_run.group(1)}}, sort_keys=False)

#         # fallback: treat as a visual query click
#         return yaml.safe_dump({"action": {"type": "query_click", "query": desc}}, sort_keys=False)



# # If run as a script, demonstrate basic usage (very small example).
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.DEBUG)
#     agent = MainAIAgent()
#     prompt = "Open Google and search for 'pyautogui screenshot example'"
#     yaml_out = agent.plan(prompt)
#     print("=== PLAN YAML ===")
#     print(yaml_out)




# os_automation/agents/main_ai.py

import os
import yaml
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI   # Official client

logger = logging.getLogger(__name__)

class MainAIAgent:
    """
    LLM-driven planner + replan logic.
    Produces atomic OS micro-steps compatible with ExecutorAgent + ValidatorAgent.
    """

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # -----------------------------------------------------
    # Step 1 — High-level → micro-plan
    # -----------------------------------------------------
    def plan(self, user_prompt: str) -> str:
        """
        Use an LLM to convert a natural-language task into micro-steps.
        MUST produce atomic actions, never combined steps.
        """

        system_prompt = """
You are an OS automation planner.
Your job is to decompose a user's instruction into **atomic GUI micro-steps**.

RULES:
- NEVER combine actions.
- EACH step must contain exactly ONE of:
    - "Open the browser"
    - "Click <something>"
    - "Type 'text'"
    - "Press Enter"
    - "Scroll Down" / "Scroll Up"
    - "Open Terminal"
    - "Run command 'xxx'"
- Text typed must ALWAYS be placed in single quotes.
- Always produce YAML with:
steps:
  - step_id: 1
    description: "..."
  - step_id: 2
    description: "..."

Examples:

User: "Search for dogs on Google"
Output:
steps:
  - step_id: 1
    description: "Open the browser"
  - step_id: 2
    description: "Click search box"
  - step_id: 3
    description: "Type 'dogs'"
  - step_id: 4
    description: "Press Enter"

User: "List files in my terminal"
Output:
steps:
  - step_id: 1
    description: "Open Terminal"
  - step_id: 2
    description: "Type 'ls'"
  - step_id: 3
    description: "Press Enter"
""".strip()

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

        text = response.choices[0].message.content

        # Ensure valid YAML
        try:
            parsed = yaml.safe_load(text)
            if not isinstance(parsed, dict) or "steps" not in parsed:
                raise ValueError("Planner returned invalid YAML")
            return text
        except Exception as e:
            logger.error("Planner failed to produce YAML: %s", text)
            raise e

    # -----------------------------------------------------
    # Step 2 — Replan on failure
    # -----------------------------------------------------
    def replan_on_failure(self, user_prompt: str, failed_step_yaml: str, failure_details_yaml: str) -> str:
        """
        Ask the LLM to fix ONLY the failed step.
        Produce new micro-steps as YAML.
        """

        system_prompt = """
You are an OS automation replanner.
Your job is to FIX a failed micro-step and produce a corrected step list.

RULES:
- NEVER retry the same failing action.
- Produce ONLY micro-steps.
- Keep steps atomic.
- Output only YAML with structure:
steps:
  - step_id: 100
    description: "..."
  - step_id: 101
    description: "..."
""".strip()

        content = f"""
The user prompt was:
{user_prompt}

The failing step was:
{failed_step_yaml}

Validation + execution details:
{failure_details_yaml}

Now generate corrected micro-steps that can fix the failure.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ]
        )

        text = response.choices[0].message.content

        # Validate YAML
        try:
            parsed = yaml.safe_load(text)
            if "steps" not in parsed:
                raise ValueError("Replan output invalid")
            return text
        except:
            # deterministic escalation
            return yaml.safe_dump({
                "escalation": {
                    "reason": "step_failed_4_times",
                    "original_prompt": user_prompt,
                    "failed_step": yaml.safe_load(failed_step_yaml),
                    "failure_details": yaml.safe_load(failure_details_yaml),
                    "suggested_manual_steps": [
                        "Manually inspect the before/after screenshots.",
                        "Check if the UI changed.",
                        "Try writing a more explicit instruction."
                    ]
                }
            }, sort_keys=False)
            
            
    def decide_event_llm(self, description: str, bbox: Optional[list] = None, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Ask the LLM what action to take for this step given a bbox (or screenshot).
        Returns a dict like: {"event": "click"} or {"event": "type", "text": "X"} or {"event": "keypress", "key":"enter"}.
        This method uses a constrained-response prompt and attempts to parse JSON from the model.
        """
        import json, textwrap
        system = textwrap.dedent("""
        You are an OS automation decision helper. Given a single short GUI instruction and optionally
        a bounding box (area) or screenshot context, choose the best action from the following:
         - click
         - click_at (include coords)
         - double_click
         - right_click
         - type (include text)
         - keypress (include key like 'enter')
         - scroll (direction up/down)
         - noop (do nothing / wait)
        Output MUST be a single JSON object on one line with keys:
         - event: one of the above
         - text: optional (for type)
         - key: optional (for keypress)
         - coords: optional [x,int,y,int] for click_at
        Example valid output: {"event":"click"} or {"event":"type","text":"hello"}.
        Keep output strictly JSON (no extra commentary).
        """)
        user_content = f"Instruction: {description}\nBbox: {bbox}\nImagePath: {image_path}\nDecide the best single event."
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=200
            )
            text = resp.choices[0].message.content.strip()

            # Try parse JSON (model might reply clean JSON). If it returns code fence, strip it.
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            jtext = m.group(0) if m else text

            parsed = json.loads(jtext)
            # normalize keys
            evt = {"event": parsed.get("event")}
            if parsed.get("text"):
                evt["text"] = parsed.get("text")
            if parsed.get("key"):
                evt["key"] = parsed.get("key")
            if parsed.get("coords"):
                evt["coords"] = parsed.get("coords")
            return evt
        except Exception as e:
            # on failure, fallback to safe local heuristic (caller can handle)
            logger.debug("decide_event_llm failed: %s", e)
            return {"event": "unknown"}

