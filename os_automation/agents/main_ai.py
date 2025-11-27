# # os_automation/agents/main_ai.py

# import os
# import yaml
# import logging
# from typing import List, Dict, Any, Optional
# from openai import OpenAI   # Official client

# logger = logging.getLogger(__name__)


# import re  # you already use re in decide_event_llm, but if it's not imported globally, add this.

# def _extract_raw_yaml_block(text: str) -> str:
#     """
#     Normalize model output:
#     - If it contains a ```yaml ... ``` fenced block, extract the inner YAML.
#     - Otherwise, return the text as-is.
#     """
#     if not text:
#         return text

#     # Match ```yaml ... ``` or ```yml ... ``` or just ``` ... ```
#     fence_pattern = re.compile(
#         r"```(?:yaml|yml)?\s*(.*?)```",
#         re.DOTALL | re.IGNORECASE
#     )
#     m = fence_pattern.search(text)
#     if m:
#         return m.group(1).strip()

#     return text.strip()


# class MainAIAgent:
#     """
#     LLM-driven planner + replan logic.
#     Produces atomic OS micro-steps compatible with ExecutorAgent + ValidatorAgent.
#     """

#     def __init__(self, model: str = "gpt-4o"):
#         self.model = model
#         self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

#     # -----------------------------------------------------
#     # Step 1 — High-level → micro-plan
#     # -----------------------------------------------------
#     def plan(self, user_prompt: str) -> str:
#         """
#         Use an LLM to convert a natural-language task into micro-steps.
#         MUST produce atomic actions, never combined steps.
#         """

#         system_prompt = """
# You are an OS automation planner.
# Your job is to decompose a user's instruction into **atomic GUI micro-steps**.

# RULES:
# - NEVER combine actions.
# - EACH step must contain exactly ONE of:
#     - "Open the browser"
#     - "Click <something>"
#     - "Type 'text'"
#     - "Press Enter"
#     - "Scroll Down" / "Scroll Up"
#     - "Open Terminal"
#     - "Run command 'xxx'"
# - Text typed must ALWAYS be placed in single quotes.
# - Always produce YAML with:
# steps:
#   - step_id: 1
#     description: "..."
#   - step_id: 2
#     description: "..."

# Examples:

# User: "Search for dogs on Google"
# Output:
# steps:
#   - step_id: 1
#     description: "Open the browser"
#   - step_id: 2
#     description: "Click search box"
#   - step_id: 3
#     description: "Type 'dogs'"
#   - step_id: 4
#     description: "Press Enter"

# User: "List files in my terminal"
# Output:
# steps:
#   - step_id: 1
#     description: "Open Terminal"
#   - step_id: 2
#     description: "Type 'ls'"
#   - step_id: 3
#     description: "Press Enter"
# """.strip()

#         response = self.client.chat.completions.create(
#             model=self.model,
#             temperature=0,
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_prompt},
#             ]
#         )

#         text = response.choices[0].message.content

#         # Ensure valid YAML
#         try:
#             parsed = yaml.safe_load(text)
#             if not isinstance(parsed, dict) or "steps" not in parsed:
#                 raise ValueError("Planner returned invalid YAML")
#             return text
#         except Exception as e:
#             logger.error("Planner failed to produce YAML: %s", text)
#             raise e

#     # -----------------------------------------------------
#     # Step 2 — Replan on failure
#     # -----------------------------------------------------
#     def replan_on_failure(self, user_prompt: str, failed_step_yaml: str, failure_details_yaml: str) -> str:
#         """
#         Ask the LLM to fix ONLY the failed step.
#         Produce new micro-steps as YAML.
#         """

#         system_prompt = """
# You are an OS automation replanner.
# Your job is to FIX a failed micro-step and produce a corrected step list.

# RULES:
# - NEVER retry the same failing action.
# - Produce ONLY micro-steps.
# - Keep steps atomic.
# - Output only YAML with structure:
# steps:
#   - step_id: 100
#     description: "..."
#   - step_id: 101
#     description: "..."
# """.strip()

#         content = f"""
# The user prompt was:
# {user_prompt}

# The failing step was:
# {failed_step_yaml}

# Validation + execution details:
# {failure_details_yaml}

# Now generate corrected micro-steps that can fix the failure.
# """

#         response = self.client.chat.completions.create(
#             model=self.model,
#             temperature=0,
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": content},
#             ]
#         )

#         text = response.choices[0].message.content

#         # Validate YAML
#         try:
#             parsed = yaml.safe_load(text)
#             if "steps" not in parsed:
#                 raise ValueError("Replan output invalid")
#             return text
#         except:
#             # deterministic escalation
#             return yaml.safe_dump({
#                 "escalation": {
#                     "reason": "step_failed_4_times",
#                     "original_prompt": user_prompt,
#                     "failed_step": yaml.safe_load(failed_step_yaml),
#                     "failure_details": yaml.safe_load(failure_details_yaml),
#                     "suggested_manual_steps": [
#                         "Manually inspect the before/after screenshots.",
#                         "Check if the UI changed.",
#                         "Try writing a more explicit instruction."
#                     ]
#                 }
#             }, sort_keys=False)
            
            
#     def decide_event_llm(self, description: str, bbox: Optional[list] = None, image_path: Optional[str] = None) -> Dict[str, Any]:
#         """
#         Ask the LLM what action to take for this step given a bbox (or screenshot).
#         Returns a dict like: {"event": "click"} or {"event": "type", "text": "X"} or {"event": "keypress", "key":"enter"}.
#         This method uses a constrained-response prompt and attempts to parse JSON from the model.
#         """
#         import json, textwrap
#         system = textwrap.dedent("""
#         You are an OS automation decision helper. Given a single short GUI instruction and optionally
#         a bounding box (area) or screenshot context, choose the best action from the following:
#          - click
#          - click_at (include coords)
#          - double_click
#          - right_click
#          - type (include text)
#          - keypress (include key like 'enter')
#          - scroll (direction up/down)
#          - noop (do nothing / wait)
#         Output MUST be a single JSON object on one line with keys:
#          - event: one of the above
#          - text: optional (for type)
#          - key: optional (for keypress)
#          - coords: optional [x,int,y,int] for click_at
#         Example valid output: {"event":"click"} or {"event":"type","text":"hello"}.
#         Keep output strictly JSON (no extra commentary).
#         """)
#         user_content = f"Instruction: {description}\nBbox: {bbox}\nImagePath: {image_path}\nDecide the best single event."
#         try:
#             resp = self.client.chat.completions.create(
#                 model=self.model,
#                 temperature=0.0,
#                 messages=[
#                     {"role": "system", "content": system},
#                     {"role": "user", "content": user_content}
#                 ],
#                 max_tokens=200
#             )
#             text = resp.choices[0].message.content.strip()

#             # Try parse JSON (model might reply clean JSON). If it returns code fence, strip it.
#             import re
#             m = re.search(r"\{.*\}", text, re.DOTALL)
#             jtext = m.group(0) if m else text

#             parsed = json.loads(jtext)
#             # normalize keys
#             evt = {"event": parsed.get("event")}
#             if parsed.get("text"):
#                 evt["text"] = parsed.get("text")
#             if parsed.get("key"):
#                 evt["key"] = parsed.get("key")
#             if parsed.get("coords"):
#                 evt["coords"] = parsed.get("coords")
#             return evt
#         except Exception as e:
#             # on failure, fallback to safe local heuristic (caller can handle)
#             logger.debug("decide_event_llm failed: %s", e)
#             return {"event": "unknown"}


#     def rewrite_ui_query(self, description: str) -> Optional[str]:
#         """
#         Convert a UI description like:
#             'Click first link'
#         into a short visual query like:
#             'YouTube'
#             'first video'
#             'YouTube icon'
#             'video thumbnail'
#         """
#         system = """
# You rewrite UI descriptions into short text target queries that help detect
# GUI elements visually. 
# Output a single short phrase, no JSON, no explanation.
# Examples:
# - 'Click first link' → 'YouTube'
# - 'Click first result' → 'YouTube'
# - 'Open Gmail button' → 'Gmail'
# - 'Click profile icon' → 'profile'
# The output must be <= 3 words.
# """

#         resp = self.client.chat.completions.create(
#             model=self.model,
#             temperature=0,
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": description},
#             ]
#         )

#         return resp.choices[0].message.content.strip()


# os_automation/agents/main_ai.py

import os
import yaml
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI   # Official client

logger = logging.getLogger(__name__)


import re  # you already use re in decide_event_llm, but if it's not imported globally, add this.

def _extract_raw_yaml_block(text: str) -> str:
    """
    Normalize model output:
    - If it contains a ```yaml ... ``` fenced block, extract the inner YAML.
    - Otherwise, return the text as-is.
    """
    if not text:
        return text

    # Match ```yaml ... ``` or ```yml ... ``` or just ``` ... ```
    fence_pattern = re.compile(
        r"```(?:yaml|yml)?\s*(.*?)```",
        re.DOTALL | re.IGNORECASE
    )
    m = fence_pattern.search(text)
    if m:
        return m.group(1).strip()

    return text.strip()


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
- For commands that should be typed into a GUI terminal window:
    - ALWAYS use: "Type 'command'" + "Press Enter"
    - Do NOT use "Run command 'command'" for GUI terminal interactions.
- EACH step must contain exactly ONE of:
    - "Open the browser"
    - "Click <something>"
    - "Type 'text'"
    - "Press Enter"
    - "Scroll Down" / "Scroll Up"
    - "Open Terminal"
    - "Run command 'xxx'"
- Text typed must ALWAYS be placed in single quotes.
- Always produce YAML **without any markdown code fences**:
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

        raw_text = response.choices[0].message.content or ""
        text = _extract_raw_yaml_block(raw_text)

        # Ensure valid YAML
        try:
            parsed = yaml.safe_load(text)
            if not isinstance(parsed, dict) or "steps" not in parsed:
                raise ValueError("Planner returned invalid YAML structure")
            return text
        except Exception as e:
            logger.error("Planner failed to produce YAML: %s", raw_text)
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
- Output only YAML with structure, and DO NOT wrap it in markdown fences:
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

        raw_text = response.choices[0].message.content or ""
        text = _extract_raw_yaml_block(raw_text)

        # Validate YAML
        try:
            parsed = yaml.safe_load(text)
            if "steps" not in parsed:
                raise ValueError("Replan output invalid")
            return text
        except Exception:
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


    def rewrite_ui_query(self, description: str) -> Optional[str]:
        """
        Convert a UI description like:
            'Click first link'
        into a short visual query like:
            'YouTube'
            'first video'
            'YouTube icon'
            'video thumbnail'
        """
        system = """
You rewrite UI descriptions into short text target queries that help detect
GUI elements visually. 
Output a single short phrase, no JSON, no explanation.
Examples:
- 'Click first link' → 'YouTube'
- 'Click first result' → 'YouTube'
- 'Open Gmail button' → 'Gmail'
- 'Click profile icon' → 'profile'
The output must be <= 3 words.
"""

        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": description},
            ]
        )

        return resp.choices[0].message.content.strip()

