# # os_automation/agents/main_ai.py
# import os
# import yaml
# import requests
# from typing import List, Dict, Any
# from os_automation.core.tal import PlannedStep
# import logging
# logger = logging.getLogger(__name__)

# class MainAIAgent:
#     """
#     Planner agent:
#     - Tries local LLM endpoint at http://localhost:8002/generate (assumed for DeepSeek/DeepSeek-like).
#     - If not available, falls back to OpenAI if OPENAI_API_KEY present.
#     - Otherwise uses a simple rule-based splitter to produce steps.
#     Returns list[PlannedStep].
#     """

#     LOCAL_LLM_URL = os.environ.get("LOCAL_LLM_URL", "http://localhost:8002/generate")
#     OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

#     def __init__(self, planner_model: str = None):
#         self.planner_model = planner_model

#     def _call_local_llm(self, prompt: str) -> str:
#         try:
#             r = requests.post(self.LOCAL_LLM_URL, json={"prompt": prompt, "max_tokens": 512}, timeout=10)
#             r.raise_for_status()
#             return r.json().get("text") or r.json().get("result") or r.text
#         except Exception as e:
#             logger.debug("Local LLM not available: %s", e)
#             raise

#     def _call_openai(self, prompt: str) -> str:
#         try:
#             import openai
#             openai.api_key = self.OPENAI_API_KEY
#             resp = openai.ChatCompletion.create(
#                 model="gpt-4",
#                 messages=[{"role":"user","content":prompt}],
#                 max_tokens=512,
#                 temperature=0.1
#             )
#             return resp.choices[0].message.content
#         except Exception as e:
#             logger.debug("OpenAI call failed: %s", e)
#             raise

#     def _simple_planner(self, user_prompt: str) -> List[Dict[str, Any]]:
#         # Very basic fallback: split on sentences and number them.
#         steps = []
#         sentences = [s.strip() for s in user_prompt.replace("\n", " ").split('.') if s.strip()]
#         for i, s in enumerate(sentences, start=1):
#             steps.append({"step_id": i, "description": s})
#         if not steps:
#             steps = [{"step_id": 1, "description": user_prompt}]
#         return steps

#     def plan(self, user_prompt: str) -> List[PlannedStep]:
#         """
#         Return a list of PlannedStep objects.
#         The planner asks LLM to return YAML with "steps" list where each item has id and description.
#         Example YAML expected:
#         steps:
#           - step_id: 1
#             description: "Click on the Search box"
#           - step_id: 2
#             description: "Type 'hello' and press Enter"
#         """
#         prompt = (
#             "You are an automation plan generator. Given the user instruction, produce a YAML "
#             "document containing a top-level 'steps' list. Each step must have 'step_id' (int) and 'description' (string). "
#             "Be concise. Return ONLY YAML and no other commentary.\n\n"
#             f"User instruction: '''{user_prompt}'''\n\nYAML:"
#         )

#         planner_text = None

#         # Try local LLM first
#         try:
#             planner_text = self._call_local_llm(prompt)
#         except Exception:
#             # Try OpenAI if configured
#             if self.OPENAI_API_KEY:
#                 try:
#                     planner_text = self._call_openai(prompt)
#                 except Exception:
#                     planner_text = None

#         if planner_text:
#             # Extract YAML from text (be forgiving)
#             try:
#                 # If model returned markdown code fence, strip it
#                 if "```" in planner_text:
#                     planner_text = planner_text.split("```")[-2]
#                 data = yaml.safe_load(planner_text)
#                 if isinstance(data, dict) and "steps" in data:
#                     steps = data["steps"]
#                     planned = []
#                     for s in steps:
#                         sid = int(s.get("step_id") if s.get("step_id") is not None else s.get("id", 0))
#                         desc = s.get("description", str(s))
#                         planned.append(PlannedStep(step_id=sid, description=desc))
#                     return planned
#             except Exception as e:
#                 logger.debug("Failed to parse planner output as YAML: %s", e)
#                 planner_text = None

#         # final fallback: rule-based
#         raw = self._simple_planner(user_prompt)
#         planned = [PlannedStep(step_id=s["step_id"], description=s["description"]) for s in raw]
#         return planned

# # os_automation/agents/main_ai.py

import os
import yaml
import logging
import re
from typing import List
from os_automation.core.tal import PlannedStep

logger = logging.getLogger(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

# ⚠️ If you are NOT running a localhost model → disable the URL completely
LOCAL_LLM_URL = None


# --------------------------------------------------------
# ✨ Utility: Extract search text or quoted text
# --------------------------------------------------------
def extract_quoted_text(prompt: str):
    m = re.search(r"'([^']+)'|\"([^\"]+)\"", prompt)
    if m:
        return m.group(1) if m.group(1) else m.group(2)
    return None


# --------------------------------------------------------
# ✨ Utility: Extract URL (google.com etc.)
# --------------------------------------------------------
def extract_url(prompt: str):
    m = re.search(r"(https?://[^\s]+|[\w\-]+\.[a-zA-Z]{2,})", prompt)
    return m.group(1) if m else None


class MainAIAgent:
    """
    Planner agent that ALWAYS returns atomic UI steps.
    If OpenAI is available → use it to create YAML steps.
    If OpenAI fails → fallback to a deterministic micro-step generator.
    """

    def __init__(self, planner_model: str = "gpt-4"):
        self.planner_model = planner_model

    # --------------------------------------------------------
    # 🔧 Call OpenAI for planning
    # --------------------------------------------------------
    def _call_openai(self, prompt: str) -> str:
        if not OPENAI_KEY:
            return None

        try:
            import openai
            openai.api_key = OPENAI_KEY

            resp = openai.ChatCompletion.create(
                model=self.planner_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.0
            )
            return resp.choices[0].message.content

        except Exception as e:
            logger.debug("OpenAI planner failed: %s", e)
            return None

    # --------------------------------------------------------
    # 🔧 (Optional) Local LLM
    # --------------------------------------------------------
    def _call_local(self, prompt: str) -> str:
        if not LOCAL_LLM_URL:
            return None

        try:
            import requests
            r = requests.post(LOCAL_LLM_URL, json={"prompt": prompt}, timeout=10)
            r.raise_for_status()
            return r.json().get("text")
        except Exception as e:
            logger.debug("Local LLM call failed: %s", e)
            return None

    # --------------------------------------------------------
    # ⭐ Fallback Micro-Step Generator (critical improvement)
    # --------------------------------------------------------
    def _micro_step_fallback(self, user_prompt: str):
        """
        Strong fallback: ALWAYS produce atomic UI steps.
        This makes your agent behave like OpenComputerUse even without LLM.
        """

        steps = []
        sid = 1

        # 1️⃣ ALWAYS ensure browser is opened
        steps.append({"step_id": sid, "description": "open browser"})
        sid += 1

        # 2️⃣ URL detection
        url = extract_url(user_prompt)
        search_term = extract_quoted_text(user_prompt)

        # Visit a URL if present
        if url:
            steps.append({"step_id": sid, "description": "click address bar"})
            sid += 1

            steps.append({"step_id": sid, "description": f"type '{url}'"})
            sid += 1

            steps.append({"step_id": sid, "description": "press enter"})
            sid += 1

        # 3️⃣ Search box + enter
        if search_term:
            steps.append({"step_id": sid, "description": "click search box"})
            sid += 1

            steps.append({"step_id": sid, "description": f"type '{search_term}'"})
            sid += 1

            steps.append({"step_id": sid, "description": "press enter"})
            sid += 1

        # 4️⃣ Fallback: if no info found, create at least 1 atomic step
        if len(steps) == 1:  # only "open browser"
            steps.append({"step_id": 2, "description": user_prompt})

        return steps

    # --------------------------------------------------------
    # ⭐ MAIN planning function
    # --------------------------------------------------------
    def plan(self, user_prompt: str) -> List[PlannedStep]:
        """
        1. Try OpenAI YAML planner
        2. Try Local LLM
        3. Fallback: Micro-step deterministic planner
        """

        # --------------------------------------------------------
        # 1️⃣ Build planner prompt
        # --------------------------------------------------------
        prompt = (
            "You are an automation planner. Convert the user instruction into ATOMIC UI steps.\n"
            "Return ONLY valid YAML with a top-level key 'steps'.\n"
            "Each step must contain:\n"
            "- step_id: integer\n"
            "- description: string (one single atomic UI action)\n\n"
            "Examples of atomic actions:\n"
            "- open browser\n"
            "- click address bar\n"
            "- type 'google.com'\n"
            "- press enter\n"
            "- click search box\n"
            "- type 'hello world'\n\n"
            "User instruction:\n"
            f"'''{user_prompt}'''\n\n"
            "YAML:"
        )

        # --------------------------------------------------------
        # 2️⃣ Try OpenAI first
        # --------------------------------------------------------
        text = self._call_openai(prompt)

        # --------------------------------------------------------
        # 3️⃣ Try Local LLM second
        # --------------------------------------------------------
        if not text:
            text = self._call_local(prompt)

        # --------------------------------------------------------
        # 4️⃣ If LLM produced something → parse YAML
        # --------------------------------------------------------
        if text:
            try:
                # extract YAML from markdown fenced blocks
                if "```" in text:
                    for block in text.split("```"):
                        if block.strip().startswith("steps"):
                            text = block
                            break

                # force extraction
                idx = text.find("steps:")
                if idx != -1:
                    text = text[idx:]

                parsed = yaml.safe_load(text)

                if isinstance(parsed, dict) and "steps" in parsed:
                    planned = [
                        PlannedStep(step_id=s.get("step_id"), description=s.get("description"))
                        for s in parsed["steps"]
                    ]
                    # VALID YAML → skip fallback
                    return planned

            except Exception as e:
                logger.debug("Planner YAML parse failed: %s", e)

        # --------------------------------------------------------
        # 5️⃣ Fallback → deterministic micro-step generator
        # --------------------------------------------------------
        logger.debug("Planner falling back to micro-step mode.")
        fallback_steps = self._micro_step_fallback(user_prompt)

        return [
            PlannedStep(step_id=s["step_id"], description=s["description"])
            for s in fallback_steps
        ]
