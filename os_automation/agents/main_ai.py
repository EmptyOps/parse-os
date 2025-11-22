# os_automation/agents/main_ai.py
"""
Main planner agent (YAML in / YAML out).

- plan(user_prompt: str) -> str  : returns YAML with top-level 'steps' (list of dicts)
- replan_on_failure(original_prompt, failed_step_yaml, failure_details_yaml) -> str
    : returns YAML with either revised 'steps' or an 'escalation' object.

This file merges features from the newer and older variants:
- OpenAI (chat completion) planner (if OPENAI_API_KEY set)
- Optional LOCAL LLM POST endpoint
- Robust YAML extraction & validation
- Deterministic micro-step fallback
"""
from __future__ import annotations

import os
import re
import yaml
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

# If you have a localhost LLM endpoint (text-in/text-out), set it here.
# If not using, leave as None.
LOCAL_LLM_URL: Optional[str] = None


# -----------------------------
# Utilities: extractors
# -----------------------------
def extract_url(prompt: str) -> Optional[str]:
    """Find first URL or domain-like token in prompt."""
    m = re.search(r"(https?://[^\s'\"<>]+|[\w\-]+\.[a-zA-Z]{2,})", prompt)
    return m.group(1) if m else None


def extract_quoted_text(prompt: str) -> Optional[str]:
    """Find first quoted phrase (single or double quotes)."""
    m = re.search(r"'([^']+)'|\"([^\"]+)\"", prompt)
    if m:
        return m.group(1) if m.group(1) else m.group(2)
    return None


def extract_yaml_from_text(text: str) -> Optional[str]:
    """
    Attempt to extract YAML block that contains a top-level 'steps:' or 'escalation:' key.
    Looks inside fenced code blocks, otherwise searches for 'steps:' index to end.
    Returns YAML string or None.
    """
    if not text:
        return None

    # If fenced code blocks exist, check each for a steps: or escalation:
    if "```" in text:
        blocks = text.split("```")
        for b in blocks:
            if re.search(r"^\s*(steps|escalation)\s*:", b, re.MULTILINE):
                return b.strip()

    # Otherwise find first "steps:" or "escalation:" and return from there to the end.
    m = re.search(r"(steps|escalation)\s*:", text)
    if m:
        idx = m.start()
        return text[idx:].strip()

    return None


def validate_steps_obj(obj: Any) -> bool:
    """
    Validate that obj is a dict with 'steps' key and that each step is dict with
    integer step_id and string description.
    """
    try:
        if not isinstance(obj, dict) or "steps" not in obj:
            return False
        steps = obj["steps"]
        if not isinstance(steps, list) or len(steps) == 0:
            return False
        for s in steps:
            if not isinstance(s, dict):
                return False
            if "step_id" not in s or "description" not in s:
                return False
            # step_id must be int-like
            sid = s["step_id"]
            if not isinstance(sid, int):
                # allow numeric strings convertible to int
                try:
                    int(sid)
                except Exception:
                    return False
            if not isinstance(s["description"], str):
                return False
        return True
    except Exception:
        return False


# -----------------------------
# Main agent
# -----------------------------
class MainAIAgent:
    """
    Planner agent — YAML IN/OUT.

    plan(user_prompt: str) -> str  # YAML text with top-level 'steps'
    replan_on_failure(...) -> str  # YAML text with either revised 'steps' or 'escalation'
    """

    def __init__(self, planner_model: str = "gpt-4"):
        self.planner_model = planner_model

    # -------------------------
    # LLM calls
    # -------------------------
    def _call_openai(self, prompt: str, max_tokens: int = 600) -> Optional[str]:
        if not OPENAI_KEY:
            return None
        try:
            import openai
            openai.api_key = OPENAI_KEY

            # Use ChatCompletion for backward compatibility
            resp = openai.ChatCompletion.create(
                model=self.planner_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            content = resp.choices[0].message.content
            return content
        except Exception as e:
            logger.debug("OpenAI call failed: %s", e, exc_info=True)
            return None

    def _call_local(self, prompt: str, timeout: int = 10) -> Optional[str]:
        if not LOCAL_LLM_URL:
            return None
        try:
            import requests
            r = requests.post(LOCAL_LLM_URL, json={"prompt": prompt}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # Expect either {"text": "..."} or {"response": "..."} or raw string
            text = None
            if isinstance(data, dict):
                text = data.get("text") or data.get("response") or data.get("result")
            if not text:
                # fallback: if server returned a single string
                if isinstance(data, str):
                    text = data
            return text
        except Exception as e:
            logger.debug("Local LLM call failed: %s", e, exc_info=True)
            return None

    # -------------------------
    # Deterministic micro-fallback
    # -------------------------
        # -------------------------
    # Deterministic micro-fallback
    # -------------------------
    def _micro_fallback(self, user_prompt: str) -> List[Dict[str, Any]]:
        """
        Deterministic fallback that respects the Planner Agent rules:

        - Output is a list of steps, each with:
            step_id: int
            description: string (one atomic UI action)
        - No login steps.
        - No 'open browser' unless the USER explicitly requested opening Chrome/browser.
        - Steps should be executable by the ExecutorAgent.
        """
        steps: List[Dict[str, Any]] = []
        sid = 1
        low = (user_prompt or "").lower()

        # -------------------------------
        # 1) TERMINAL / SHELL INTENT
        # -------------------------------
        terminal_keywords = [
            "terminal", "open terminal", "shell", "bash", "zsh",
            "run command", "execute", "ls", "pwd", "cat", "mkdir",
            "list out the files", "list files", "list directory"
        ]
        if any(k in low for k in terminal_keywords):
            # Step 1: open the terminal
            steps.append({"step_id": sid, "description": "open terminal"})
            sid += 1

            quoted = extract_quoted_text(user_prompt)

            # If user explicitly mentions listing files / directory
            if "list out the files" in low or "list files" in low or "list directory" in low:
                steps.append({"step_id": sid, "description": "run command 'ls -la'"})
                sid += 1
                return steps

            # If a command is provided in quotes
            if quoted:
                steps.append({"step_id": sid, "description": f"run command '{quoted}'"})
                sid += 1
                return steps

            # Try to extract command after "run" or "execute"
            m = re.search(r"(?:run|execute)\s+`?\"?([^`'\"]+)`?\"?", user_prompt, re.IGNORECASE)
            if m:
                cmd = m.group(1).strip()
                steps.append({"step_id": sid, "description": f"run command '{cmd}'"})
                sid += 1
                return steps

            # Fallback: just open terminal and wait for user
            steps.append({"step_id": sid, "description": "wait for command"})
            return steps

        # -------------------------------
        # 2) BROWSER / SEARCH INTENT
        # -------------------------------
        search_keywords = [
            "google", "search", "internet", "website", "browse",
            "look up", "search for", "find on google"
        ]
        browser_open_intent = any(
            kw in low for kw in ["open browser", "open chrome", "open google chrome"]
        )

        if any(k in low for k in search_keywords) or browser_open_intent:
            # 🔹 Important: According to your Planner template,
            # we assume Chrome is already open for generic web tasks.
            # So we only add "open browser" if the *user explicitly asked* to open it.
            if browser_open_intent:
                steps.append({"step_id": sid, "description": "open browser"})
                sid += 1

            quoted = extract_quoted_text(user_prompt)
            if quoted:
                steps.append({"step_id": sid, "description": "click search box"})
                sid += 1
                steps.append({"step_id": sid, "description": f"type '{quoted}'"})
                sid += 1
                steps.append({"step_id": sid, "description": "press enter"})
                sid += 1
                return steps

        # -------------------------------
        # 3) RAW QUOTED INPUT (UNKNOWN CONTEXT)
        #    – Safe default: treat as typing into a search/input box
        # -------------------------------
        quoted = extract_quoted_text(user_prompt)
        if quoted:
            steps.append({"step_id": sid, "description": "click search box"})
            sid += 1
            steps.append({"step_id": sid, "description": f"type '{quoted}'"})
            sid += 1
            steps.append({"step_id": sid, "description": "press enter"})
            sid += 1
            return steps

        # -------------------------------
        # 4) URL NAVIGATION
        # -------------------------------
        url = extract_url(user_prompt)
        if url:
            # Only open browser if explicitly requested (otherwise assume it is already open)
            if browser_open_intent:
                steps.append({"step_id": sid, "description": "open browser"})
                sid += 1
            steps.append({"step_id": sid, "description": "click address bar"})
            sid += 1
            steps.append({"step_id": sid, "description": f"type '{url}'"})
            sid += 1
            steps.append({"step_id": sid, "description": "press enter"})
            sid += 1
            return steps

        # -------------------------------
        # 5) FALLBACK: Treat instruction as *one* atomic UI step
        # -------------------------------
        steps.append({"step_id": sid, "description": user_prompt})
        return steps


    # -------------------------
    # Plan function (YAML out)
    # -------------------------
    def plan(self, user_prompt: str) -> str:
        """
        Convert user instruction into YAML steps. Always returns YAML text with top-level 'steps'.

        Communication contract:
        - Planner → Orchestrator: YAML string with:
            steps:
              - step_id: <int>
                description: <atomic UI action>

        This matches your Planner Agent template:
        - Assume Chrome is already open for web tasks.
        - Assume Gmail is already logged in (never add login steps).
        - Do NOT add 'open browser' unless the user explicitly asks.
        - Never execute anything yourself; only plan.
        """
        planner_prompt = (
            "You are the PLANNER AGENT for an OS automation system.\n"
            "Your ONLY job is to convert the user's request into a clear list of ATOMIC UI STEPS.\n\n"
            "ASSUMPTIONS:\n"
            "1. If the task involves a web browser, assume Google Chrome is ALREADY OPEN.\n"
            "2. If the task involves Gmail, assume the user is ALREADY LOGGED IN.\n"
            "   - Therefore, NEVER include steps such as 'open Chrome', 'go to gmail.com', or any login steps,\n"
            "     UNLESS the user explicitly asks you to open the browser.\n\n"
            "RULES:\n"
            "- Break down the request into small, deterministic UI actions.\n"
            "- Each step MUST be ONE atomic UI operation (click, type, press key, scroll, etc.).\n"
            "- Steps must be executable by a separate Executor Agent.\n"
            "- Do NOT execute anything yourself. Only plan.\n"
            "- Keep descriptions concrete and UI-specific (e.g. 'click search box', 'type \"invoice\"').\n\n"
            "OUTPUT FORMAT (STRICT):\n"
            "Return ONLY valid YAML, no prose, with this shape:\n"
            "steps:\n"
            "  - step_id: 1\n"
            "    description: \"Click on the email search bar\"\n"
            "  - step_id: 2\n"
            "    description: \"Type the word 'invoice'\"\n\n"
            "CONSTRAINTS:\n"
            "- The top-level key MUST be 'steps'.\n"
            "- Each step MUST have:\n"
            "  - step_id: integer (1, 2, 3, ...)\n"
            "  - description: string (one atomic UI action)\n"
            "- Do NOT wrap the YAML in Markdown code fences.\n\n"
            f"User instruction:\n'''{user_prompt}'''\n\nYAML:"
        )

        text: Optional[str] = None

        # 1) Try OpenAI
        text = self._call_openai(planner_prompt)

        # 2) Try local LLM endpoint if OpenAI unavailable
        if not text:
            text = self._call_local(planner_prompt)

        # 3) If LLM responded, try to extract + validate YAML
        if text:
            yaml_candidate = extract_yaml_from_text(text)
            if yaml_candidate:
                try:
                    parsed = yaml.safe_load(yaml_candidate)
                    if validate_steps_obj(parsed):
                        # canonical YAML with top-level 'steps' and step_id fields
                        yaml_text = yaml.safe_dump({"steps": parsed["steps"]}, sort_keys=False)
                        return yaml_text
                    else:
                        logger.debug("Parsed planner YAML didn't validate as 'steps' object. parsed=%s", parsed)
                except Exception as e:
                    logger.debug("Error parsing planner YAML candidate: %s", e, exc_info=True)
            else:
                logger.debug("Planner LLM output contained no YAML candidate.")

        # 4) Fallback: deterministic micro-step generator
        logger.debug("Planner falling back to deterministic micro-steps.")
        fallback_steps = self._micro_fallback(user_prompt)
        yaml_text = yaml.safe_dump({"steps": fallback_steps}, sort_keys=False)
        return yaml_text

    

    # # -------------------------
    # # Plan function (YAML out)
    # # -------------------------
    # def plan(self, user_prompt: str) -> str:
    #     """
    #     Convert user instruction into YAML steps. Always returns YAML text with top-level 'steps'.
    #     Order of attempts:
    #      1. OpenAI ChatCompletion (if key present)
    #      2. Local LLM (if configured)
    #      3. Deterministic micro-fallback
    #     """
    #     # Build planner prompt (strict instructions to return YAML only)
    #     planner_prompt = (
    #         "You are an automation planner. Convert the user instruction into ATOMIC UI steps.\n"
    #         "Return ONLY valid YAML with a top-level key 'steps'. Each step must have:\n"
    #         "- step_id: integer\n"
    #         "- description: string (one single atomic UI action)\n\n"
    #         "Examples of atomic actions:\n"
    #         "- open browser\n"
    #         "- click address bar\n"
    #         "- click search box\n"
    #         "- type 'hello world'\n\n"
    #         "Constraints:\n"
    #         "- Return only YAML (no surrounding prose).\n"
    #         "- Keep steps atomic and ordered.\n\n"
    #         f"User instruction:\n'''{user_prompt}'''\n\nYAML:"
    #     )

    #     text: Optional[str] = None

    #     # Try OpenAI
    #     text = self._call_openai(planner_prompt)

    #     # Try local LLM if OpenAI not available / failed
    #     if not text:
    #         text = self._call_local(planner_prompt)

    #     # If we got some LLM output attempt to extract YAML and validate it.
    #     if text:
    #         yaml_candidate = extract_yaml_from_text(text)
    #         if yaml_candidate:
    #             # try parsing
    #             try:
    #                 parsed = yaml.safe_load(yaml_candidate)
    #                 if validate_steps_obj(parsed):
    #                     # produce a clean YAML string (stable ordering)
    #                     yaml_text = yaml.safe_dump({"steps": parsed["steps"]}, sort_keys=False)
    #                     return yaml_text
    #                 else:
    #                     logger.debug("Parsed YAML didn't validate as 'steps' object. parsed=%s", parsed)
    #             except Exception as e:
    #                 logger.debug("Error parsing YAML candidate: %s", e, exc_info=True)
    #         else:
    #             logger.debug("LLM output contained no YAML candidate.")

    #     # Fallback: deterministic micro-step generator
    #     logger.debug("Planner falling back to deterministic micro-steps.")
    #     fallback_steps = self._micro_fallback(user_prompt)
    #     yaml_text = yaml.safe_dump({"steps": fallback_steps}, sort_keys=False)
    #     return yaml_text

    # -------------------------
    # Replan on failure / escalation
    # -------------------------
    def replan_on_failure(self, original_prompt: str, failed_step_yaml: str, failure_details_yaml: str) -> str:
        """
        Called when a step failed repeatedly. Attempt to use LLM to propose:
          - a revised 'steps' YAML, OR
          - an 'escalation' block with reason/diagnostics/suggested_manual_steps
        If LLM fails, return deterministic escalation YAML.
        """
        system_msg = (
            "You are an automation planner. A previous execution failed repeatedly.\n"
            "Given the original user prompt, the failed step (as YAML), and failure details (as YAML), either produce:\n"
            "1) a revised YAML plan under 'steps', or\n"
            "2) an 'escalation' object with fields: reason, diagnostics, suggested_manual_steps.\n\n"
            "Return only YAML."
        )

        user_msg = (
            f"Original prompt:\n'''{original_prompt}'''\n\n"
            f"Failed step (YAML):\n{failed_step_yaml}\n\n"
            f"Failure details (YAML):\n{failure_details_yaml}\n\n"
            "Return only YAML. Make the escalation actionable (specific selectors/observations if possible)."
        )

        combined_prompt = f"{system_msg}\n\n{user_msg}"

        # Try OpenAI
        text: Optional[str] = None
        text = self._call_openai(combined_prompt, max_tokens=800)

        # Try local
        if not text:
            text = self._call_local(combined_prompt)

        if text:
            candidate = extract_yaml_from_text(text)
            if candidate:
                try:
                    parsed = yaml.safe_load(candidate)
                    # accept either validated 'steps' or an 'escalation' dict
                    if isinstance(parsed, dict) and ("steps" in parsed or "escalation" in parsed):
                        # If 'steps' present and valid, return it canonicalized
                        if "steps" in parsed and validate_steps_obj(parsed):
                            yaml_text = yaml.safe_dump({"steps": parsed["steps"]}, sort_keys=False)
                            return yaml_text
                        # If escalation present, return canonicalized escalation
                        if "escalation" in parsed:
                            yaml_text = yaml.safe_dump({"escalation": parsed["escalation"]}, sort_keys=False)
                            return yaml_text
                        # If steps present but not strictly valid - still return it (best-effort)
                        if "steps" in parsed:
                            yaml_text = yaml.safe_dump({"steps": parsed.get("steps")}, sort_keys=False)
                            return yaml_text
                except Exception as e:
                    logger.debug("Failed to parse replan LLM YAML candidate: %s", e, exc_info=True)
            else:
                logger.debug("Replan LLM output had no YAML candidate.")

        # Deterministic escalation fallback
        logger.debug("Replan falling back to deterministic escalation.")
        try:
            failed_step = None
            failure_details = None
            try:
                failed_step = yaml.safe_load(failed_step_yaml)
            except Exception:
                failed_step = {"raw": failed_step_yaml}

            try:
                failure_details = yaml.safe_load(failure_details_yaml)
            except Exception:
                failure_details = {"raw": failure_details_yaml}

            escalation = {
                "escalation": {
                    "reason": "step_failed_4_times",
                    "original_prompt": original_prompt,
                    "failed_step": failed_step,
                    "failure_details": failure_details,
                    "suggested_manual_steps": [
                        "Manually inspect the 'before' and 'after' screenshots referenced in failure_details.",
                        "Check if the UI text/labels/selectors have changed since the plan was authored.",
                        "If necessary, re-run the planner with an explicit instruction such as: "
                        "'Click the button labeled \"Continue\" in the top-right corner of the page.'"
                    ]
                }
            }
            return yaml.safe_dump(escalation, sort_keys=False)
        except Exception as e:
            logger.exception("Failed to build deterministic escalation: %s", e)
            # return a minimal escalation YAML
            return yaml.safe_dump({
                "escalation": {
                    "reason": "unknown_error",
                    "original_prompt": original_prompt,
                    "message": "Unable to generate escalation details programmatically."
                }
            }, sort_keys=False)

    
    # -------------------------
    # ActionAgent (YAML in / YAML out) — placed inside MainAIAgent for single-agent constraint
    # -------------------------
    def action_for_yaml(self, yaml_request: str) -> str:
        """
        YAML in:
          action_request:
            description: "click the Save button"
            screenshot: "/path/to/shot.png"

        YAML out:
          action:
            type: "query_click" | "click_at" | "type" | "run_command" | "open_terminal" | ...
            query: "Save button"        # for query_click
            coords: [x, y]              # for click_at
            bbox: [x,y,w,h]             # optionally
            text: "hello"               # for type
            command: "ls -la"           # for run_command
            key: "enter"                # for keypress
            meta: {...}
        """
        try:
            req = yaml.safe_load(yaml_request) or {}
        except Exception:
            # return a safe default YAML action
            return yaml.safe_dump({"action": {"type": "query_click", "query": yaml_request}}, sort_keys=False)

        ar = req.get("action_request", {})
        desc = (ar.get("description") or "").strip()
        shot = ar.get("screenshot")

        # Try LLM function-calling if configured
        if OPENAI_KEY:
            try:
                import openai, json
                openai.api_key = OPENAI_KEY

                functions = [
                    {
                        "name": "produce_action",
                        "description": "Produce a structured YAML action for UI automation",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "query": {"type": "string"},
                                "text": {"type": "string"},
                                "command": {"type": "string"},
                                "coords": {"type": "array", "items": {"type": "integer"}},
                                "bbox": {"type": "array", "items": {"type": "integer"}},
                                "key": {"type": "string"},
                                "meta": {"type": "object"}
                            },
                            "required": ["type"]
                        }
                    }
                ]

                messages = [
                    {"role": "system", "content": "Translate a single atomic UI instruction to a structured action. Return a single function call 'produce_action' with JSON arguments only."},
                    {"role": "user", "content": desc}
                ]

                resp = openai.ChatCompletion.create(
                    model=self.planner_model,
                    messages=messages,
                    functions=functions,
                    function_call={"name": "produce_action"},
                    temperature=0.0,
                )

                func_call = resp.choices[0].message.get("function_call")
                if func_call and func_call.get("arguments"):
                    args_text = func_call.get("arguments")
                    try:
                        parsed = json.loads(args_text)
                        return yaml.safe_dump({"action": parsed}, sort_keys=False)
                    except Exception:
                        logger.debug("ActionAgent: couldn't parse function args, falling back to rules.")
            except Exception as e:
                logger.debug("ActionAgent LLM call failed: %s", e, exc_info=True)

        # Deterministic fallback (rules)
        # Common patterns:
        m_type = re.search(r"type\s+['\"]([^'\"]+)['\"]", desc)
        if m_type:
            action = {"type": "type", "text": m_type.group(1)}
            return yaml.safe_dump({"action": action}, sort_keys=False)

        m_clickat = re.search(r"click\s+at\s+(\d+)[,\s]+(\d+)", desc, re.IGNORECASE)
        if m_clickat:
            action = {"type": "click_at", "coords": [int(m_clickat.group(1)), int(m_clickat.group(2))]}
            return yaml.safe_dump({"action": action}, sort_keys=False)

        if "terminal" in desc.lower() and "run command" not in desc.lower():
            return yaml.safe_dump({"action": {"type": "open_terminal"}}, sort_keys=False)


        if "open browser" in desc.lower() or "chrome" in desc.lower() or "firefox" in desc.lower():
            return yaml.safe_dump({"action": {"type": "open_browser"}}, sort_keys=False)

        m_run = re.search(r"run\s+command\s+['\"]([^'\"]+)['\"]", desc, re.IGNORECASE)
        if m_run:
            return yaml.safe_dump({"action": {"type": "run_command", "command": m_run.group(1)}}, sort_keys=False)

        # fallback: treat as a visual query click
        return yaml.safe_dump({"action": {"type": "query_click", "query": desc}}, sort_keys=False)



# If run as a script, demonstrate basic usage (very small example).
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    agent = MainAIAgent()
    prompt = "Open Google and search for 'pyautogui screenshot example'"
    yaml_out = agent.plan(prompt)
    print("=== PLAN YAML ===")
    print(yaml_out)


