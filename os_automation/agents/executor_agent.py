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
from typing import Optional, List, Dict, Any
from PIL import Image
import pyautogui
import requests

from os_automation.core.registry import registry
from os_automation.repos.osatlas_adapter import _parse_position_raw, normalize_coordinates, draw_big_dot

logger = logging.getLogger(__name__)

# load optional openai key
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

class ExecutorAgent:
    def __init__(self, default_detection="osatlas", default_executor="pyautogui", openai_model="gpt-4"):
        self.default_detection = default_detection
        self.default_executor = default_executor
        self.openai_model = openai_model
        self.OPENAI_KEY = OPENAI_KEY
        self.output_dir = os.path.join(os.getcwd(), "os_automation_output")
        os.makedirs(self.output_dir, exist_ok=True)

    def _screenshot(self, prefix="shot") -> str:
        fname = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
        path = os.path.join(self.output_dir, fname)
        try:
            img = pyautogui.screenshot()
            img.save(path)
            return path
        except Exception as e:
            logger.exception("screenshot failed: %s", e)
            # fallback blank image
            Image.new("RGB", (800, 600), (255,255,255)).save(path)
            return path

    def detect_bbox_for_step(self, step_description: str, image_path: Optional[str] = None, tries: int = 3) -> Optional[List[int]]:
        """
        Use OSAtlas adapter (grounding model) to get bbox/point and normalize it.
        Returns [x,y,w,h]
        """
        det_factory = registry.get_adapter(self.default_detection)
        if det_factory is None:
            logger.warning("No detection adapter registered: %s", self.default_detection)
            return None
        det = det_factory() if callable(det_factory) else det_factory

        for attempt in range(tries):
            shot = image_path or self._screenshot("shot")
            payload = {"image_path": shot, "text": step_description}
            try:
                res = None
                # prefer detect method
                for fn in ("detect","run","predict","infer"):
                    try:
                        if hasattr(det, fn):
                            res = getattr(det, fn)(payload)
                            break
                    except Exception:
                        continue
                if res is None:
                    # try as a callable
                    if callable(det):
                        res = det(payload)
            except Exception as e:
                logger.debug("detection adapter error: %s", e)
                res = None

            if res:
                # unify shapes
                if isinstance(res, dict):
                    if "bbox" in res:
                        bx = res["bbox"]
                        # accept [x,y,w,h] or [x1,y1,x2,y2]
                        if len(bx) >= 4:
                            x,y,w,h = bx[0],bx[1],bx[2],bx[3]
                            # if provided as x1,y1,x2,y2 convert
                            if x >= 0 and y >= 0 and (w > 1000 or h > 1000 or bx[2] > bx[0]):
                                # assume x1,y1,x2,y2
                                x1,y1,x2,y2 = bx[:4]
                                cx = int((x1 + x2)/2)
                                cy = int((y1 + y2)/2)
                                w = int(abs(x2-x1))
                                h = int(abs(y2-y1))
                                x = cx - w//2
                                y = cy - h//2
                            return [int(x), int(y), int(w), int(h)]
                    if "point" in res:
                        pt = res["point"]
                        parsed = _parse_position_raw(pt)
                        if parsed:
                            nx, ny = normalize_coordinates(parsed, shot)
                            # small bbox
                            return [nx-10, ny-10, 20, 20]
                # sometimes returns raw list
                if isinstance(res, (list, tuple)) and len(res) >= 2:
                    parsed = _parse_position_raw(res)
                    if parsed:
                        nx, ny = normalize_coordinates(parsed, shot)
                        return [nx-10, ny-10, 20, 20]

            time.sleep(0.4)
        return None

    def decide_event_with_llm(self, step_description: str, bbox: List[int]) -> Dict[str, Any]:
        """
        Uses OpenAI (if configured) to return {"event": "click"|"type"|..., "text": ...}
        Otherwise use heuristics.
        """
        heuristic = {"event":"click","text":None}
        lower = step_description.lower()
        if "type" in lower or "search" in lower or "enter" in lower or "'" in step_description or '"' in step_description:
            import re
            m = re.search(r"['\"](.+?)['\"]", step_description)
            heuristic = {"event":"type","text": m.group(1) if m else None}
        if "double" in lower:
            heuristic["event"] = "double_click"
        if "right click" in lower or "context" in lower:
            heuristic["event"] = "right_click"
        if "scroll" in lower:
            heuristic["event"] = "scroll"

        if not self.OPENAI_KEY:
            return heuristic

        try:
            import openai
            openai.api_key = self.OPENAI_KEY
            prompt = (
                "You are a UI execution planner. Given the step description and detected bbox, "
                "return STRICT JSON only with keys: event (one of click, double_click, right_click, type, scroll, noop), "
                "and text (string|null). Example: {\"event\":\"type\",\"text\":\"hello\"}\n\n"
                f"Step description: {step_description}\nDetected bbox: {bbox}\n\nReturn JSON:"
            )
            resp = openai.ChatCompletion.create(
                model=self.openai_model,
                messages=[{"role":"user","content":prompt}],
                max_tokens=128,
                temperature=0.0
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[-2].strip()
            if "{" in content:
                start = content.find("{")
                end = content.rfind("}")+1
                content = content[start:end]
            parsed = json.loads(content)
            return {"event": parsed.get("event"), "text": parsed.get("text")}
        except Exception as e:
            logger.debug("LLM decision failed: %s", e)
            return heuristic

    def _perform_action(self, bbox: List[int], event: str, text: Optional[str] = None) -> Dict[str,Any]:
        """
        Low-level executor using pyautogui (or executor adapter).
        Returns dict with status, before, after.
        """
        before = self._screenshot("before")
        x = int(bbox[0] + bbox[2]/2)
        y = int(bbox[1] + bbox[3]/2)

        try:
            # move and action
            pyautogui.moveTo(x, y, duration=0.12)
            time.sleep(0.06)
            if event == "click":
                pyautogui.click()
            elif event == "double_click":
                pyautogui.doubleClick()
            elif event == "right_click":
                pyautogui.rightClick()
            elif event == "type":
                if text is not None:
                    pyautogui.click()
                    time.sleep(0.05)
                    # type with slight interval
                    pyautogui.write(str(text), interval=0.01)
            elif event == "scroll":
                pyautogui.scroll(-200)  # scroll down; heuristic
            elif event == "noop":
                pass
            else:
                pyautogui.click()
        except Exception as e:
            logger.exception("Execution error: %s", e)
            after = self._screenshot("after")
            return {"status":"failed","before":before,"after":after,"error":str(e)}

        # let UI render
        time.sleep(0.8)
        after = self._screenshot("after")
        return {"status":"success","before":before,"after":after}

    def run_step(self, step_description: str, validator_agent, max_attempts: int = 3) -> Dict[str,Any]:
        """
        High level: detect -> decide -> execute -> validate (with retries).
        Returns structured execution+validation result.
        """
        attempt = 0
        final_exec = None
        final_validation = None

        while attempt < max_attempts:
            attempt += 1
            logger.info("Attempt %d for step: %s", attempt, step_description)
            shot = self._screenshot("shot")
            bbox = self.detect_bbox_for_step(step_description, image_path=shot)
            if not bbox:
                logger.info("No bbox found for step '%s' on attempt %d", step_description, attempt)
                time.sleep(0.5)
                continue

            # show debug overlay saved for inspection (optional)
            try:
                img = Image.open(shot)
                cx = int(bbox[0] + bbox[2] / 2)
                cy = int(bbox[1] + bbox[3] / 2)
                dot = draw_big_dot(img, (cx, cy))
                dot_fp = ...
                dot.save(dot_fp)
            except Exception as e:
                logger.debug(f"Debug overlay failed: {e}")


            decision = self.decide_event_with_llm(step_description, bbox)
            event = decision.get("event") or "click"
            text = decision.get("text")

            exec_out = self._perform_action(bbox, event, text)
            exec_out["bbox"] = bbox
            exec_out["decision"] = decision

            validation = validator_agent.validate_step({"description": step_description}, {
                "before": exec_out.get("before"),
                "after": exec_out.get("after"),
                "raw": exec_out
            })

            logger.info("Validation result: %s", validation)
            final_exec = exec_out
            final_validation = validation

            if validation.get("validation_status") == "pass":
                break

            time.sleep(0.4)

        return {"execution": final_exec, "validation": final_validation}
