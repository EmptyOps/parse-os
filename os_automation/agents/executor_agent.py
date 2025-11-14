# # os_automation/agents/executor_agent.py
# import os
# import time
# import uuid
# from typing import Dict, Any
# from PIL import Image
# import logging

# from os_automation.core.registry import registry

# logger = logging.getLogger(__name__)

# # Try to import pyautogui for screenshots and fallback gracefully
# try:
#     import pyautogui
# except Exception:
#     pyautogui = None

# class ExecutorAgent:
#     """
#     Executes planned steps:
#     - For each step: use detection adapter (e.g., osatlas) to find bbox (needs image_path)
#     - Take screenshot before -> call execution adapter (pyautogui) -> take screenshot after
#     - Returns a dict with status and paths to screenshots
#     """

#     def __init__(self, default_detection="omniparser", default_executor="pyautogui"):
#         self.default_detection = default_detection
#         self.default_executor = default_executor

#     def _screenshot(self, name_prefix="shot") -> str:
#         fname = f"{name_prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
#         out = os.path.join(os.getcwd(), "os_automation_output")
#         os.makedirs(out, exist_ok=True)
#         path = os.path.join(out, fname)
#         try:
#             if pyautogui:
#                 img = pyautogui.screenshot()
#                 img.save(path)
#             else:
#                 # use PIL fallback: a tiny blank image if pyautogui not present
#                 Image.new("RGB", (200, 200), color=(255,255,255)).save(path)
#             return path
#         except Exception as e:
#             logger.exception("Failed to take screenshot: %s", e)
#             # create placeholder
#             Image.new("RGB", (200, 200), color=(255,255,255)).save(path)
#             return path

#     def execute(self, bbox: list, event: str, executor_name: str = None, text: str = None) -> Dict[str, Any]:
#         """
#         bbox: [x,y,w,h]
#         event: "click"/"type"/"scroll"/...
#         executor_name: adapter name (e.g. pyautogui)
#         text: text to type if event == "type"
#         """
#         executor_name = executor_name or self.default_executor
#         exec_adapter_factory = registry.get_adapter(executor_name)
#         if exec_adapter_factory is None:
#             return {"status": "failed", "reason": f"executor adapter '{executor_name}' not registered"}

#         exec_adapter = exec_adapter_factory() if callable(exec_adapter_factory) else exec_adapter_factory

#         before = self._screenshot("before")
#         # Build step payload expected by adapter.execute
#         step_payload = {"bbox": bbox, "event": event, "text": text}
#         try:
#             result = exec_adapter.execute(step_payload)
#         except Exception as e:
#             logger.exception("Execution adapter error: %s", e)
#             result = {"status": "failed", "detail": str(e)}

#         after = self._screenshot("after")
#         return {"status": result.get("status", "failed"), "before": before, "after": after, "raw": result}


# os_automation/agents/executor_agent.py
import os
import time
import uuid
import json
import logging
from typing import Dict, Any, Optional
from PIL import Image

from os_automation.core.registry import registry

logger = logging.getLogger(__name__)

# Try to import pyautogui for screenshots and fallback gracefully
try:
    import pyautogui
except Exception:
    pyautogui = None

class ExecutorAgent:
    """
    Executes planned steps:
    - For each step: use detection adapter (e.g., osatlas) to find bbox (needs image_path)
    - Ask OpenAI which event to perform on that bbox (click/type/scroll/etc.)
    - Run execution adapter (pyautogui)
    """

    def __init__(self, default_detection="osatlas", default_executor="pyautogui", openai_model: str = "gpt-4"):
        self.default_detection = default_detection
        self.default_executor = default_executor
        self.openai_model = openai_model
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    def _screenshot(self, name_prefix="shot") -> str:
        fname = f"{name_prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
        out = os.path.join(os.getcwd(), "os_automation_output")
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, fname)
        try:
            if pyautogui:
                img = pyautogui.screenshot()
                img.save(path)
            else:
                Image.new("RGB", (200, 200), color=(255, 255, 255)).save(path)
            return path
        except Exception as e:
            logger.exception("Failed to take screenshot: %s", e)
            Image.new("RGB", (200, 200), color=(255,255,255)).save(path)
            return path

    def detect_bbox_for_step(self, step_description: str, image_path: Optional[str] = None) -> Optional[list]:
        """
        Ask the detection adapter to find a bbox for the given human description and screenshot.
        Adapter interface is forgiving:
          - try .detect(payload) then .run(payload) then call factory with payload.
        Expected to return [x,y,w,h] or None.
        """
        det_name = self.default_detection
        det_factory = registry.get_adapter(det_name)
        if det_factory is None:
            logger.warning("Detection adapter '%s' not registered", det_name)
            return None

        det = det_factory() if callable(det_factory) else det_factory
        payload = {"image_path": image_path, "text": step_description}

        # Try common method names
        for fn in ("detect", "run", "predict", "infer"):
            try:
                if hasattr(det, fn):
                    res = getattr(det, fn)(payload)
                    # accept various shapes: dict with 'bbox', list, or nested
                    if isinstance(res, dict):
                        if "bbox" in res:
                            return res["bbox"]
                        if "bboxes" in res and len(res["bboxes"]) > 0:
                            return res["bboxes"][0]
                        # sometimes return {'result': [{'bbox':...}]}
                        if "result" in res and isinstance(res["result"], list) and len(res["result"])>0:
                            r0 = res["result"][0]
                            if isinstance(r0, dict) and "bbox" in r0:
                                return r0["bbox"]
                    elif isinstance(res, (list, tuple)) and len(res) >= 4 and all(isinstance(x, (int, float)) for x in res[:4]):
                        return list(res[:4])
            except Exception as e:
                logger.debug("Detection adapter method %s failed: %s", fn, e)
                continue
        logger.debug("Detection adapter did not return bbox for '%s'", step_description)
        return None

    def decide_event_with_llm(self, step_description: str, bbox: list) -> Dict[str, Any]:
        """
        Ask OpenAI (if configured) to decide the event on this bbox.
        Expected return: {"event": "click"|"double_click"|"type"|"scroll"|"noop", "text": "..."}
        If OpenAI not configured, use a simple heuristic: if step contains 'type' or quotes -> type.
        """
        # fallback heuristic
        heuristic = {"event": "click", "text": None}
        lower = step_description.lower()
        if "type" in lower or "enter" in lower or "'" in step_description or '"' in step_description:
            # try to extract quoted text
            import re
            m = re.search(r"['\"](.+?)['\"]", step_description)
            heuristic = {"event": "type", "text": m.group(1) if m else None}
        elif "scroll" in lower:
            heuristic = {"event": "scroll", "text": None}

        if not self.OPENAI_API_KEY:
            return heuristic

        try:
            import openai
            openai.api_key = self.OPENAI_API_KEY
            prompt = (
                "You are an automation execution planner. For the UI element described below, "
                "decide the most appropriate low-level event to perform and return strictly JSON only.\n\n"
                f"Step description: {step_description}\n"
                f"Detected bbox: {bbox}\n\n"
                "Return JSON with keys: event (one of: click, double_click, right_click, type, scroll, noop), "
                "and text (string or null). Example: {\"event\":\"type\",\"text\":\"hello world\"}\n"
            )
            resp = openai.ChatCompletion.create(
                model=self.openai_model,
                messages=[{"role":"user","content":prompt}],
                max_tokens=128,
                temperature=0.0
            )
            content = resp.choices[0].message.content.strip()
            # Accept either raw JSON or code fences
            if content.startswith("```"):
                content = content.split("```")[-2].strip()
            # Some models return YAML or sentence; try to extract JSON using first { ... }
            if "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_blob = content[start:end]
            else:
                json_blob = content
            parsed = json.loads(json_blob)
            return {"event": parsed.get("event"), "text": parsed.get("text")}
        except Exception as e:
            logger.debug("LLM event decision failed: %s", e)
            return heuristic

    def execute(self, bbox: list, event: str, executor_name: str = None, text: str = None) -> Dict[str, Any]:
        """
        Low-level execution: uses executor adapter (e.g., pyautogui adapter)
        """
        executor_name = executor_name or self.default_executor
        exec_adapter_factory = registry.get_adapter(executor_name)
        if exec_adapter_factory is None:
            return {"status": "failed", "reason": f"executor adapter '{executor_name}' not registered"}

        exec_adapter = exec_adapter_factory() if callable(exec_adapter_factory) else exec_adapter_factory

        before = self._screenshot("before")
        step_payload = {"bbox": bbox, "event": event, "text": text}
        try:
            result = exec_adapter.execute(step_payload)
        except Exception as e:
            logger.exception("Execution adapter error: %s", e)
            result = {"status": "failed", "detail": str(e)}

        after = self._screenshot("after")
        # normalize result
        return {"status": result.get("status", "failed"), "before": before, "after": after, "raw": result}

    def run_step(self, step_description: str, screenshot_path: Optional[str] = None, max_attempts: int = 3) -> Dict[str, Any]:
        """
        High-level: detect -> decide -> execute. Retries detection+decision up to max_attempts.
        Returns structured info for validator to consume.
        """
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            # ensure we have a screenshot; if caller didn't provide, take one
            shot = screenshot_path or self._screenshot("shot")
            bbox = self.detect_bbox_for_step(step_description, image_path=shot)
            if not bbox:
                logger.info("Attempt %d: no bbox found for '%s'", attempts, step_description)
                # retry after short wait
                time.sleep(0.5)
                continue

            decision = self.decide_event_with_llm(step_description, bbox)
            event = decision.get("event") or "click"
            text = decision.get("text")
            exec_result = self.execute(bbox=bbox, event=event, text=text)
            # attach the bbox and decision
            exec_result["bbox"] = bbox
            exec_result["decision"] = decision
            return exec_result

        # if we exit loop no bbox found
        return {"status": "failed", "reason": "no-bbox", "before": None, "after": None}

    def run_multi_step(self, planned_steps, validator_agent, max_attempts_per_step=3):
        """
        Full multi-agent orchestration INSIDE ExecutorAgent.
        - Accepts planner output (list[PlannedStep])
        - Iterates detection → event decision → execution → validation
        - Retries failed steps up to max_attempts_per_step
        - Returns final combined report

        This allows Orchestrator to run 3-agent flow WITHOUT extra coordinator file.
        """
        final_reports = []

        for step in planned_steps:
            step_desc = step.description
            step_id = step.step_id

            print(f"\n========== RUNNING STEP {step_id}: {step_desc} ==========")

            attempt = 0
            exec_result = None
            validation_result = None

            while attempt < max_attempts_per_step:
                attempt += 1
                print(f"--- Attempt {attempt} for step {step_id} ---")

                # 1️⃣ Screenshot for detection
                shot = self._screenshot("shot")

                # 2️⃣ Detect bbox
                bbox = self.detect_bbox_for_step(step_desc, image_path=shot)

                if not bbox:
                    print(f"⚠ No bbox found for step {step_id} on attempt {attempt}")
                    time.sleep(0.4)
                    continue

                # 3️⃣ Decide event
                decision = self.decide_event_with_llm(step_desc, bbox)
                event = decision.get("event") or "click"
                text = decision.get("text")

                # 4️⃣ Execute action
                exec_out = self.execute(
                    bbox=bbox,
                    event=event,
                    text=text
                )

                # 5️⃣ Prepare validation input
                exec_result = {
                    "step_id": step_id,
                    "bbox": bbox,
                    "decision": decision,
                    "before": exec_out.get("before"),
                    "after": exec_out.get("after"),
                    "status": exec_out.get("status"),
                    "raw": exec_out
                }

                # 6️⃣ Validate
                validation_result = validator_agent.validate_step(step.dict(), exec_result)

                print("Validation:", validation_result)

                if validation_result["validation_status"] == "pass":
                    break

                time.sleep(0.4)

            # Collect final report for this step
            final_reports.append({
                "step": step.dict(),
                "execution": exec_result,
                "validation": validation_result
            })

            if validation_result["validation_status"] != "pass":
                print(f"❌ Step {step_id} FAILED after {max_attempts_per_step} attempts")
                return {
                    "overall_status": "failed",
                    "steps": final_reports
                }

        return {
            "overall_status": "success",
            "steps": final_reports
        }

