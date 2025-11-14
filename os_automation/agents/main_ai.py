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


# os_automation/agents/main_ai.py
import os
import yaml
import requests
import logging
from typing import List, Dict, Any
from os_automation.core.tal import PlannedStep

logger = logging.getLogger(__name__)

class MainAIAgent:
    """
    Planner agent:
    - Prefer OpenAI (if OPENAI_API_KEY present) to generate YAML plan.
    - Fallback to local LLM at LOCAL_LLM_URL if OpenAI fails or not configured.
    - Final fallback: simple rule-based splitter.
    Returns list[PlannedStep].
    """

    LOCAL_LLM_URL = os.environ.get("LOCAL_LLM_URL", "http://localhost:8002/generate")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    def __init__(self, planner_model: str = "gpt-4"):
        self.planner_model = planner_model

    def _call_local_llm(self, prompt: str) -> str:
        try:
            r = requests.post(self.LOCAL_LLM_URL, json={"prompt": prompt, "max_tokens": 512}, timeout=10)
            r.raise_for_status()
            return r.json().get("text") or r.json().get("result") or r.text
        except Exception as e:
            logger.debug("Local LLM not available: %s", e)
            raise

    def _call_openai(self, prompt: str) -> str:
        try:
            import openai
            openai.api_key = self.OPENAI_API_KEY
            resp = openai.ChatCompletion.create(
                model=self.planner_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.0
            )
            print("🔑 OpenAI API key is call")
            return resp.choices[0].message.content
        except Exception as e:
            logger.debug("OpenAI call failed: %s", e)
            raise

    def _simple_planner(self, user_prompt: str) -> List[Dict[str, Any]]:
        steps = []
        # better splitting: split by ; or . or newline
        import re
        sentences = [s.strip() for s in re.split(r'[;\.\n]+', user_prompt) if s.strip()]
        for i, s in enumerate(sentences, start=1):
            steps.append({"step_id": i, "description": s})
        if not steps:
            steps = [{"step_id": 1, "description": user_prompt}]
        return steps

    def plan(self, user_prompt: str) -> List[PlannedStep]:
        prompt = (
            "You are an automation plan generator. Given the user instruction, produce a YAML "
            "document containing a top-level 'steps' list. Each step must have 'step_id' (int) and 'description' (string). "
            "Be concise. Return ONLY YAML and no other commentary.\n\n"
            f"User instruction: '''{user_prompt}'''\n\nYAML:"
        )

        planner_text = None

        # Prefer OpenAI if available
        if self.OPENAI_API_KEY:
            try:
                planner_text = self._call_openai(prompt)
            except Exception:
                planner_text = None

        # then try local LLM
        if planner_text is None:
            try:
                planner_text = self._call_local_llm(prompt)
            except Exception:
                planner_text = None

        if planner_text:
            try:
                # strip triple-backtick fences and optional language markers
                if "```" in planner_text:
                    # take inner code block if present
                    parts = planner_text.split("```")
                    # try to find block that looks like YAML
                    inner = None
                    for p in parts:
                        if p.strip().lstrip().startswith("steps"):
                            inner = p
                            break
                    planner_text = inner or parts[-2] if len(parts) >= 2 else planner_text
                # afford forgiving: sometimes models add leading text; attempt to find 'steps:' start
                idx = planner_text.find("steps:")
                if idx != -1:
                    planner_text = planner_text[idx:]
                data = yaml.safe_load(planner_text)
                if isinstance(data, dict) and "steps" in data:
                    steps = data["steps"]
                    planned = []
                    for s in steps:
                        sid = int(s.get("step_id") if s.get("step_id") is not None else s.get("id", 0))
                        desc = s.get("description", str(s))
                        planned.append(PlannedStep(step_id=sid, description=desc))
                    return planned
            except Exception as e:
                logger.debug("Failed to parse planner output as YAML: %s", e)
                planner_text = None

        # final fallback: rule-based
        raw = self._simple_planner(user_prompt)
        planned = [PlannedStep(step_id=s["step_id"], description=s["description"]) for s in raw]
        return planned
