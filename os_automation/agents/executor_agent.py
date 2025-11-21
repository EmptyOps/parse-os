#os_automation/agents/executor_agent.py

import os
import time
import uuid
import yaml
import logging
import random
from typing import Optional, Dict, Any, List

from PIL import Image
import pyautogui

from os_automation.core.registry import registry
from os_automation.repos.osatlas_adapter import (
    _parse_position_raw,
    normalize_coordinates
)

logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = True


# -------------------------------------------------------
# Screenshot helper
# -------------------------------------------------------
def _screenshot(output_dir: str, prefix="shot") -> str:
    fname = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
    path = os.path.join(output_dir, fname)
    try:
        img = pyautogui.screenshot()
        img.save(path)
        return path
    except Exception as e:
        logger.debug("screenshot failed: %s", e)
        Image.new("RGB", (800, 600), (255, 255, 255)).save(path)
        return path


# ========================================================================
#                           EXECUTOR AGENT
# ========================================================================
class ExecutorAgent:
    """
    YAML-driven executor agent.
    """

    def __init__(
        self,
        default_detection: str = "osatlas",
        default_executor: str = "pyautogui",
        openai_model: str = "gpt-4",
        chrome_preference: bool = True,
        output_dir: str = None
    ):
        self.default_detection = default_detection
        self.default_executor = default_executor
        self.openai_model = openai_model
        self.chrome_preference = chrome_preference

        self.output_dir = output_dir or os.path.join(os.getcwd(), "os_automation_output")
        os.makedirs(self.output_dir, exist_ok=True)

        try:
            pyautogui.FAILSAFE = True
        except:
            pass


    # ====================================================================
    # Chrome Stabilization Layer
    # ====================================================================
    def _stabilize_chrome(self, warmup_time: float = 1.2):
        """
        Ensures Chrome window is predictable:
        - closes "restore" dialog
        - dismisses profile picker
        - maximizes
        - focuses address bar (CTRL+L)
        """

        time.sleep(warmup_time)

        # Close unwanted dialogs
        for _ in range(2):
            try:
                pyautogui.press("esc")
                time.sleep(0.2)
            except:
                pass

        # Maximize (Linux, Windows, most DE's)
        try:
            pyautogui.hotkey("alt", "space")
            time.sleep(0.2)
            pyautogui.press("x")
            time.sleep(0.5)
        except:
            pass

        # Focus omnibox
        try:
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.3)
        except:
            pass

        time.sleep(0.2)


    # ====================================================================
    # DETECTOR LOADING
    # ====================================================================
    def _get_detection_adapter(self):
        factory = registry.get_adapter(self.default_detection)
        if factory is None:
            return None
        return factory() if callable(factory) else factory


    # ====================================================================
    # DETECT BBOX
    # ====================================================================
    def _detect_bbox(self, description: str, image_path: Optional[str] = None) -> Optional[List[int]]:
        det = self._get_detection_adapter()
        shot = image_path or _screenshot(self.output_dir, "shot")
        if not det:
            return None

        try:
            for fn in ("detect", "call", "run", "predict", "infer"):
                if hasattr(det, fn):
                    try:
                        res = getattr(det, fn)({"image_path": shot, "text": description})
                        if isinstance(res, dict) and "bbox" in res:
                            bx = res["bbox"]
                            if len(bx) >= 4:
                                x, y, w, h = bx[:4]
                                if (w > 1000 or h > 1000) or (bx[2] > bx[0] and bx[3] > bx[1]):
                                    x1, y1, x2, y2 = bx[:4]
                                    w = abs(x2 - x1)
                                    h = abs(y2 - y1)
                                    x = min(x1, x2)
                                    y = min(y1, y2)
                                return [int(x), int(y), int(max(1,w)), int(max(1,h))]

                        # point detector
                        if isinstance(res, (list, tuple)) and len(res) >= 2:
                            parsed = _parse_position_raw(res)
                            if parsed:
                                nx, ny = normalize_coordinates(parsed, shot)
                                return [nx - 10, ny - 10, 20, 20]

                    except Exception as inner_e:
                        logger.debug("inner detection error: %s", inner_e)

        except Exception as e:
            logger.debug("detection adapter error: %s", e)

        return None


    # ====================================================================
    # DECISION: click / type / enter
    # ====================================================================
        # ====================================================================
    # DECISION: Fully patched event mapping (supports 15+ actions)
    # ====================================================================
    def _decide_event(self, description: str) -> Dict[str, Any]:
        import re

        desc = description.strip().lower()

        # -----------------------------------------------------------
        # TYPE WITH QUOTED TEXT  → type with payload
        # -----------------------------------------------------------
        m = re.search(r"type\s+['\"]([^'\"]+)['\"]", description, re.IGNORECASE)
        if m:
            return {"event": "type", "text": m.group(1)}

        # -----------------------------------------------------------
        # TYPE ANYTHING INSIDE QUOTES (fallback)
        # -----------------------------------------------------------
        m2 = re.search(r"['\"]([^'\"]+)['\"]", description)
        if "type" in desc and m2:
            return {"event": "type", "text": m2.group(1)}

        # -----------------------------------------------------------
        # PRESS ENTER
        # -----------------------------------------------------------
        if "press enter" in desc or desc == "enter":
            return {"event": "keypress", "key": "enter"}

        # -----------------------------------------------------------
        # BACKSPACE
        # -----------------------------------------------------------
        if "backspace" in desc:
            return {"event": "keypress", "key": "backspace"}

        # -----------------------------------------------------------
        # DELETE
        # -----------------------------------------------------------
        if "delete" in desc and "backspace" not in desc:
            return {"event": "keypress", "key": "delete"}

        # -----------------------------------------------------------
        # SELECT ALL (CTRL+A)
        # -----------------------------------------------------------
        if "select all" in desc or "ctrl+a" in desc:
            return {"event": "hotkey", "keys": ["ctrl", "a"]}

        # -----------------------------------------------------------
        # PASTE (CTRL+V)
        # -----------------------------------------------------------
        if "paste" in desc or "ctrl+v" in desc:
            return {"event": "hotkey", "keys": ["ctrl", "v"]}

        # -----------------------------------------------------------
        # ARROW KEYS
        # -----------------------------------------------------------
        if "arrow left" in desc:
            return {"event": "keypress", "key": "left"}

        if "arrow right" in desc:
            return {"event": "keypress", "key": "right"}

        if "arrow up" in desc:
            return {"event": "keypress", "key": "up"}

        if "arrow down" in desc:
            return {"event": "keypress", "key": "down"}

        # -----------------------------------------------------------
        # SCROLL
        # -----------------------------------------------------------
        if "scroll down" in desc:
            return {"event": "scroll", "direction": "down"}

        if "scroll up" in desc:
            return {"event": "scroll", "direction": "up"}

        # -----------------------------------------------------------
        # CLICK AT SPECIFIC COORDINATES
        # Example: "click at 200, 400"
        # -----------------------------------------------------------
        mcoord = re.search(r"click\s+at\s+(\d+)[,\s]+(\d+)", desc)
        if mcoord:
            x = int(mcoord.group(1))
            y = int(mcoord.group(2))
            return {"event": "click_at", "coords": (x, y)}

        # -----------------------------------------------------------
        # DOUBLE CLICK
        # -----------------------------------------------------------
        if "double click" in desc:
            return {"event": "double_click"}

        # -----------------------------------------------------------
        # RIGHT CLICK
        # -----------------------------------------------------------
        if "right click" in desc or "context" in desc:
            return {"event": "right_click"}

        # -----------------------------------------------------------
        # FALLBACK → NORMAL CLICK
        # -----------------------------------------------------------
        if "click" in desc:
            return {"event": "click"}

        # -----------------------------------------------------------
        # FINAL FALLBACK → type raw text
        # -----------------------------------------------------------
        return {"event": "type", "text": description}



    # ====================================================================
    # SAFE CLICK
    # ====================================================================
    def _safe_click_xy(self, x: int, y: int):
        jitter = random.randint(-2, 2)
        try:
            pyautogui.moveTo(x + jitter, y + jitter, duration=0.12)
            pyautogui.click()
        except Exception as e:
            logger.debug("pyautogui click error: %s", e)


    # ====================================================================
    # PERFORM ACTION
    # ====================================================================
    def _perform(self, bbox: List[int], decision: Dict[str, Any]) -> Dict[str, Any]:
        before = _screenshot(self.output_dir, "before")

        x = int(bbox[0] + bbox[2] / 2)
        y = int(bbox[1] + bbox[3] / 2)

        try:
            event = decision.get("event")

            # CLICK
            if event == "click":
                self._safe_click_xy(x, y)

            # CLICK AT COORDINATES
            elif event == "click_at":
                cx, cy = decision["coords"]
                self._safe_click_xy(cx, cy)

            # DOUBLE CLICK
            elif event == "double_click":
                self._safe_click_xy(x, y)
                time.sleep(0.05)
                self._safe_click_xy(x, y)

            # RIGHT CLICK
            elif event == "right_click":
                pyautogui.moveTo(x, y)
                pyautogui.rightClick()

            # TYPE TEXT
            elif event == "type":
                pyautogui.moveTo(x, y)
                pyautogui.click()
                text = decision.get("text")
                if text:
                    pyautogui.write(text, interval=0.01)
                else:
                    pyautogui.press("enter")

            # KEYPRESS
            elif event == "keypress":
                key = decision["key"]
                pyautogui.press(key)

            # HOTKEY (like ctrl+a, ctrl+v)
            elif event == "hotkey":
                keys = decision["keys"]
                pyautogui.hotkey(*keys)

            # SCROLL
            elif event == "scroll":
                direction = decision["direction"]
                pyautogui.moveTo(x, y)
                pyautogui.scroll(300 if direction == "up" else -300)

            else:
                raise ValueError(f"Unknown event: {event}")

            time.sleep(0.5)

        except Exception as e:
            after = _screenshot(self.output_dir, "after")
            return {"status": "failed", "before": before, "after": after, "error": str(e)}

        after = _screenshot(self.output_dir, "after")
        return {"status": "success", "before": before, "after": after}


    # ----------------------------------------------------------------
    # NEW: YAML-driven action executor (uses OSAtlas for detection, PyAutoGUI adapter for events)
    # ----------------------------------------------------------------
    def run_action_yaml(self, action_yaml: str, validator_agent, original_prompt: str = "", max_attempts: int = 4) -> str:
        """
        Input YAML (string):
        execute:
          description: "click the save button"
          action:
            type: "query_click" | "click_at" | "type" | "run_command" | "open_terminal" | ...
            query: "Save"
            coords: [x,y]
            text: "hello"
            command: "ls -la"

        Behavior:
          - For actions that require bbox (query_click) -> use detection adapter (OSAtlas)
          - For event execution -> prefer adapter.execute (pyautogui adapter) if available
          - Validate using validator_agent.validate_step_yaml (expects YAML)
          - Retry up to (max_attempts - 1) times; on final failure (attempt == max_attempts) call MainAIAgent.replan_on_failure(...) and return replan YAML
        """
        import json
        from os_automation.core.registry import registry
        from os_automation.agents.main_ai import MainAIAgent

        try:
            payload = yaml.safe_load(action_yaml) or {}
        except Exception as e:
            # malformed YAML
            return yaml.safe_dump({
                "execution": {"status": "failed", "error": "malformed_action_yaml", "message": str(e)},
                "validation": {"validation_status": "fail"},
                "escalate": True
            }, sort_keys=False)

        exec_block = payload.get("execute") or payload.get("action_request") or payload
        description = exec_block.get("description", "")
        action = exec_block.get("action", {}) or payload.get("action")

        # pack a step structure for validator compatibility
        step = {"step_id": exec_block.get("step_id", 0), "description": description}

        # Get adapters (OSAtlas detection + PyAutoGUI executor)
        try:
            det_factory = registry.get_adapter(self.default_detection)
            det_adapter = det_factory() if callable(det_factory) else det_factory
        except Exception:
            det_adapter = None

        try:
            exec_factory = registry.get_adapter(self.default_executor)
            exec_adapter = exec_factory() if callable(exec_factory) else exec_factory
        except Exception:
            exec_adapter = None

        last_execution = None
        last_validation = None

        # Attempts loop: On attempt == max_attempts we will trigger replan if still failing
        for attempt in range(1, max_attempts + 1):
            logger.info("ExecutorAction attempt %d for action: %s", attempt, action)

            # 1) Acquire a fresh screenshot
            shot = _screenshot(self.output_dir, "shot")

            # 2) Determine bbox if needed
            bbox = None
            if action.get("type") in ("query_click",):
                # call detection adapter
                if det_adapter:
                    try:
                        # adapter's detect interface: accepts dict with image_path and text/description
                        try:
                            detect_res = det_adapter.detect({"image_path": shot, "text": action.get("query") or description})
                        except Exception:
                            # Some adapters expect (image_path, text)
                            detect_res = det_adapter.detect(shot, action.get("query") or description)

                        if isinstance(detect_res, dict) and "bbox" in detect_res and detect_res["bbox"]:
                            bbox = detect_res["bbox"]
                        else:
                            # fall back to parsing any list/tuple
                            if isinstance(detect_res, (list, tuple)) and len(detect_res) >= 2:
                                parsed = _parse_position_raw(detect_res)
                                if parsed:
                                    nx, ny = normalize_coordinates(parsed, shot)
                                    bbox = [nx - 12, ny - 12, 24, 24]
                    except Exception as de:
                        logger.debug("Detection adapter error: %s", de)

                # Last resort: center fallback
                if not bbox:
                    try:
                        from PIL import Image
                        img = Image.open(shot)
                        W, H = img.size
                        cx, cy = W // 2, H // 2
                        bbox = [max(0, cx - 50), max(0, cy - 50), 100, 100]
                        logger.warning("Query_click: falling back to center bbox for action=%s", action)
                    except Exception:
                        bbox = None

            # 3) Build execution payload depending on action type
            decision = None
            event_type = None

            if action.get("type") == "type":
                event_type = "type"
                decision = {"event": "type", "text": action.get("text")}

            elif action.get("type") == "click_at":
                event_type = "click_at"
                coords = action.get("coords") or action.get("coords", [])
                if coords and len(coords) >= 2:
                    decision = {"event": "click_at", "coords": (int(coords[0]), int(coords[1]))}
                else:
                    decision = {"event": "click"}  # fallback

            elif action.get("type") in ("query_click", "click"):
                event_type = "click"
                decision = {"event": "click"}

            elif action.get("type") == "double_click":
                event_type = "double_click"
                decision = {"event": "double_click"}

            elif action.get("type") == "right_click":
                event_type = "right_click"
                decision = {"event": "right_click"}

            elif action.get("type") == "keypress":
                event_type = "keypress"
                decision = {"event": "keypress", "key": action.get("key", "enter")}

            elif action.get("type") == "hotkey":
                event_type = "hotkey"
                decision = {"event": "hotkey", "keys": action.get("keys", ["ctrl", "v"])}

            elif action.get("type") == "scroll":
                event_type = "scroll"
                decision = {"event": "scroll", "direction": action.get("direction", "down")}

            elif action.get("type") == "run_command":
                # run system command synchronously (safer wrapper)
                cmd = action.get("command") or description
                try:
                    import shlex, subprocess
                    parts = shlex.split(cmd)
                    proc = subprocess.Popen(parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    out, err = proc.communicate(timeout=30)
                    exec_result = {"status": "success" if proc.returncode == 0 else "failed", "stdout": out, "stderr": err, "before": shot, "after": _screenshot(self.output_dir, "after")}
                except Exception as e:
                    exec_result = {"status": "failed", "error": str(e), "before": shot, "after": _screenshot(self.output_dir, "after")}

                # Validate
                exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
                validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
                validation = yaml.safe_load(validation_yaml)
                last_execution = exec_result
                last_validation = validation

                if validation.get("validation_status") == "pass":
                    return yaml.safe_dump({"execution": {"attempts": attempt, "last": last_execution}, "validation": last_validation, "escalate": False}, sort_keys=False)
                else:
                    # failed -> continue loop or escalate if last attempt
                    if attempt >= max_attempts:
                        # trigger replan
                        failed_step_yaml = yaml.safe_dump({"step": step}, sort_keys=False)
                        failure_details_yaml = yaml.safe_dump({"execution": last_execution, "validation": last_validation}, sort_keys=False)
                        ma = MainAIAgent()
                        replan_yaml = ma.replan_on_failure(original_prompt or description, failed_step_yaml, failure_details_yaml)
                        return yaml.safe_dump({"execution": {"attempts": attempt, "last": last_execution}, "validation": last_validation, "escalate": True, "replan": yaml.safe_load(replan_yaml)}, sort_keys=False)
                    else:
                        time.sleep(0.6)
                        continue

            else:
                # default fallback -> treat as click
                decision = {"event": "click"}

            # 4) Execute the decided event. Prefer adapter.execute if available.
            exec_result = None
            try:
                if exec_adapter and hasattr(exec_adapter, "execute"):
                    # Build adapter step dict
                    adapter_step = {
                        "description": description,
                        "action": action,
                        "bbox": bbox,
                        "decision": decision
                    }
                    try:
                        adapter_result = exec_adapter.execute(adapter_step)
                    except TypeError:
                        # older adapters may expect different signature
                        adapter_result = exec_adapter.execute(adapter_step)

                    # normalize adapter_result to expected dict shape
                    if isinstance(adapter_result, dict):
                        exec_result = adapter_result
                    else:
                        exec_result = {"status": "success" if adapter_result else "failed", "raw": adapter_result, "before": shot, "after": _screenshot(self.output_dir, "after")}
                else:
                    # use internal _perform -> requires bbox (fallback to tiny bbox if none)
                    use_bbox = bbox or [10, 10, 20, 20]
                    exec_result = {**self._perform(use_bbox, decision), "bbox": bbox, "decision": decision}
            except Exception as e:
                exec_result = {"status": "failed", "error": str(e), "before": shot, "after": _screenshot(self.output_dir, "after")}

            # 5) Validate
            exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
            validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
            validation = yaml.safe_load(validation_yaml)

            last_execution = exec_result
            last_validation = validation

            # If pass -> return success YAML
            if validation.get("validation_status") == "pass":
                return yaml.safe_dump({
                    "execution": {"attempts": attempt, "last": last_execution},
                    "validation": validation,
                    "escalate": False
                }, sort_keys=False)

            # If failed and we've reached the max attempts -> trigger replan
            if attempt >= max_attempts:
                failed_step_yaml = yaml.safe_dump({"step": step}, sort_keys=False)
                failure_details_yaml = yaml.safe_dump({"execution": last_execution, "validation": last_validation}, sort_keys=False)
                ma = MainAIAgent()
                replan_yaml = ma.replan_on_failure(original_prompt or description, failed_step_yaml, failure_details_yaml)

                # return escalate + replan payload (as YAML structure)
                try:
                    replan_parsed = yaml.safe_load(replan_yaml)
                except Exception:
                    replan_parsed = {"escalation": {"reason": "replan_failed_parse", "raw": replan_yaml}}

                return yaml.safe_dump({
                    "execution": {"attempts": attempt, "last": last_execution},
                    "validation": last_validation,
                    "escalate": True,
                    "replan": replan_parsed
                }, sort_keys=False)

            # else -> wait and retry
            time.sleep(0.6)

        # Fallback final
        return yaml.safe_dump({
            "execution": {"attempts": max_attempts, "last": last_execution},
            "validation": last_validation,
            "escalate": True
        }, sort_keys=False)



    # ====================================================================
    # MAIN YAML EXECUTOR
    # ====================================================================
    def run_step_yaml(self, step_yaml: str, validator_agent, max_attempts: int = 3) -> str:

        step = yaml.safe_load(step_yaml)
        description = step.get("description")
        step_id = step.get("step_id")

        # -------------------------------------------------------
        # SYSTEM ACTION: OPEN BROWSER
        # -------------------------------------------------------
        low = description.lower().strip()
        if low in ("open browser", "open the browser") or \
           "open chrome" in low or "open google chrome" in low:

            try:
                import platform, subprocess, webbrowser
                system = platform.system()

                # Linux
                if system == "Linux":
                    commands = [
                        ["google-chrome-stable", "--new-window", "https://google.com"],
                        ["google-chrome", "--new-window", "https://google.com"],
                        ["chrome", "--new-window", "https://google.com"],
                        ["chromium-browser", "--new-window", "https://google.com"],
                        ["chromium", "--new-window", "https://google.com"],
                    ]
                    launched = False
                    for cmd in commands:
                        try:
                            subprocess.Popen(cmd)
                            launched = True
                            break
                        except:
                            continue
                    if not launched:
                        subprocess.Popen(["xdg-open", "https://google.com"])

                # macOS
                elif system == "Darwin":
                    subprocess.Popen([
                        "open", "-n", "-a", "Google Chrome",
                        "--args", "--new-window", "https://google.com"
                    ])

                # Windows
                elif system.startswith("Win"):
                    try:
                        subprocess.Popen([
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            "--new-window", "https://google.com"
                        ])
                    except:
                        os.startfile("chrome")

                # fallback
                else:
                    webbrowser.open("https://google.com", new=1)

                # Stabilize Chrome UI
                self._stabilize_chrome()

                before = _screenshot(self.output_dir, "before")
                after = _screenshot(self.output_dir, "after")

                return yaml.safe_dump({
                    "execution": {"attempts": 1, "last": {"status": "success", "before": before, "after": after}},
                    "validation": {"validation_status": "pass"},
                    "escalate": False
                }, sort_keys=False)

            except Exception as e:
                return yaml.safe_dump({
                    "execution": {"attempts": 1, "last": {"error": str(e)}},
                    "validation": {"validation_status": "fail"},
                    "escalate": True
                }, sort_keys=False)


        # ====================================================================
        # NORMAL (NON-SYSTEM) EXECUTION LOOP
        # ====================================================================
        attempt = 0
        last_execution = None
        last_validation = None

        while attempt < max_attempts:
            attempt += 1
            logger.info("Executor attempt %d for step %s: %s",
                        attempt, step_id, description)

            shot = _screenshot(self.output_dir, "shot")
            bbox = self._detect_bbox(description, image_path=shot)

            if not bbox:
                before = _screenshot(self.output_dir, "before")
                pyautogui.press("enter")
                time.sleep(0.6)
                after = _screenshot(self.output_dir, "after")
                exec_result = {"status": "no_bbox", "before": before, "after": after, "bbox": None}
            else:
                decision = self._decide_event(description)
                exec_result = {**self._perform(bbox, decision), "bbox": bbox, "decision": decision}

            exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
            validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
            validation = yaml.safe_load(validation_yaml)

            last_execution = exec_result
            last_validation = validation

            if validation.get("validation_status") == "pass":
                return yaml.safe_dump({
                    "execution": {"attempts": attempt, "last": last_execution},
                    "validation": validation,
                    "escalate": False
                }, sort_keys=False)

            time.sleep(0.6)

        return yaml.safe_dump({
            "execution": {"attempts": attempt, "last": last_execution},
            "validation": last_validation,
            "escalate": True,
            "escalation_reason": "max_attempts_reached"
        }, sort_keys=False)


    # ====================================================================
    # BACKWARDS COMPATIBILITY FOR ORCHESTRATOR
    # ====================================================================
    def run_step(self, step_description: str, validator_agent, max_attempts: int = 3) -> Dict[str, Any]:
        step_payload = {"step_id": 0, "description": step_description}
        step_yaml = yaml.safe_dump(step_payload, sort_keys=False)
        result_yaml = self.run_step_yaml(step_yaml, validator_agent, max_attempts)
        try:
            return yaml.safe_load(result_yaml)
        except:
            return {
                "execution": {"attempts": 0, "last": None},
                "validation": {"validation_status": "unknown"},
                "escalate": True
            }

# # os_automation/agents/executor_agent.py

# import os
# import time
# import uuid
# import yaml
# import logging
# import random
# from typing import Optional, Dict, Any, List

# from PIL import Image
# import pyautogui

# from os_automation.core.registry import registry
# from os_automation.repos.osatlas_adapter import (
#     _parse_position_raw,
#     normalize_coordinates
# )

# logger = logging.getLogger(__name__)
# pyautogui.FAILSAFE = True


# # -------------------------------------------------------
# # Screenshot helper
# # -------------------------------------------------------
# def _screenshot(output_dir: str, prefix="shot") -> str:
#     fname = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
#     path = os.path.join(output_dir, fname)
#     try:
#         img = pyautogui.screenshot()
#         img.save(path)
#         return path
#     except Exception as e:
#         logger.debug("screenshot failed: %s", e)
#         Image.new("RGB", (800, 600), (255, 255, 255)).save(path)
#         return path


# # ========================================================================
# #                           EXECUTOR AGENT
# # ========================================================================
# class ExecutorAgent:
#     """
#     YAML-driven executor agent.
#     """

#     def __init__(
#         self,
#         default_detection: str = "osatlas",
#         default_executor: str = "pyautogui",
#         openai_model: str = "gpt-4",
#         chrome_preference: bool = True,
#         output_dir: str = None
#     ):
#         self.default_detection = default_detection
#         self.default_executor = default_executor
#         self.openai_model = openai_model
#         self.chrome_preference = chrome_preference

#         self.output_dir = output_dir or os.path.join(os.getcwd(), "os_automation_output")
#         os.makedirs(self.output_dir, exist_ok=True)

#         try:
#             pyautogui.FAILSAFE = True
#         except:
#             pass


#     # ====================================================================
#     # Chrome Stabilization Layer
#     # ====================================================================
#     def _stabilize_chrome(self, warmup_time: float = 1.2):
#         """
#         Ensures Chrome window is predictable:
#         - closes "restore" dialog
#         - dismisses profile picker
#         - maximizes
#         - focuses address bar (CTRL+L)
#         """

#         time.sleep(warmup_time)

#         # Close unwanted dialogs
#         for _ in range(2):
#             try:
#                 pyautogui.press("esc")
#                 time.sleep(0.2)
#             except:
#                 pass

#         # Maximize (Linux, Windows, most DE's)
#         try:
#             pyautogui.hotkey("alt", "space")
#             time.sleep(0.2)
#             pyautogui.press("x")
#             time.sleep(0.5)
#         except:
#             pass

#         # Focus omnibox
#         try:
#             pyautogui.hotkey("ctrl", "l")
#             time.sleep(0.3)
#         except:
#             pass

#         time.sleep(0.2)


#     # ====================================================================
#     # DETECTOR LOADING
#     # ====================================================================
#     def _get_detection_adapter(self):
#         factory = registry.get_adapter(self.default_detection)
#         if factory is None:
#             return None
#         return factory() if callable(factory) else factory


#     # ====================================================================
#     # DETECT BBOX (UPGRADED)
#     # ====================================================================
#     def _detect_bbox(self, description: str, image_path: Optional[str] = None) -> Optional[List[int]]:
#         """
#         Detect a bbox for the given description using the configured detection adapter.

#         Accepts adapter responses that include:
#           - {"bbox": [x, y, w, h], "point": [cx,cy], "confidence": 0.8, "type": "bbox"}
#           - {"point": [x,y], "confidence": 0.6}
#           - legacy list [x1,y1,x2,y2] or [x,y]
#         Returns a normalized [x,y,w,h] or None when detection fails/confidence too low.
#         """
#         det = self._get_detection_adapter()
#         shot = image_path or _screenshot(self.output_dir, "shot")
#         if not det:
#             return None

#         try:
#             # try adapter's detect / call / run / predict / infer methods
#             res = None
#             for fn in ("detect", "call", "run", "predict", "infer"):
#                 if hasattr(det, fn):
#                     try:
#                         res = getattr(det, fn)({"image_path": shot, "text": description})
#                         break
#                     except Exception as inner_e:
#                         logger.debug("inner detection error: %s", inner_e)
#                         continue

#             if res is None:
#                 return None

#             # if res is a dict with bbox/point/confidence -> handle
#             if isinstance(res, dict):
#                 # some adapters return {"bbox": None, "raw": ...}
#                 bbox = res.get("bbox")
#                 point = res.get("point")
#                 confidence = float(res.get("confidence", 1.0)) if res.get("confidence") is not None else 1.0
#                 rtype = res.get("type", "").lower() if res.get("type") else ""

#                 # Treat low confidence as no detection
#                 if confidence is not None and confidence < 0.25:
#                     logger.debug("Detection confidence too low: %s", confidence)
#                     return None

#                 # If bbox present and valid, normalize and return
#                 if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
#                     x, y, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
#                     # guard negative sizes / swapped coords
#                     if w <= 0 or h <= 0:
#                         return None
#                     # Normalize coordinates to image size
#                     x, y = normalize_coordinates([x, y], shot)
#                     return [int(x), int(y), int(w), int(h)]

#                 # Fallback: point provided — convert to small bbox
#                 if point and isinstance(point, (list, tuple)) and len(point) >= 2:
#                     px, py = int(point[0]), int(point[1])
#                     px, py = normalize_coordinates([px, py], shot)
#                     return [px - 12, py - 12, 24, 24]

#                 # Legacy: adapter sometimes returns raw bbox list directly
#                 raw = res.get("raw") or res
#                 if isinstance(raw, (list, tuple)) and len(raw) >= 4:
#                     x1, y1, x2, y2 = [int(v) for v in raw[:4]]
#                     left = min(x1, x2); top = min(y1, y2); right = max(x1, x2); bottom = max(y1, y2)
#                     w = max(1, right - left); h = max(1, bottom - top)
#                     nx, ny = normalize_coordinates([left, top], shot)
#                     return [nx, ny, w, h]

#             # If adapter returned a simple list/tuple
#             if isinstance(res, (list, tuple)):
#                 if len(res) >= 4:
#                     x1, y1, x2, y2 = [int(v) for v in res[:4]]
#                     left = min(x1, x2); top = min(y1, y2); right = max(x1, x2); bottom = max(y1, y2)
#                     w = max(1, right - left); h = max(1, bottom - top)
#                     nx, ny = normalize_coordinates([left, top], shot)
#                     return [nx, ny, w, h]
#                 if len(res) == 2:
#                     px, py = int(res[0]), int(res[1])
#                     px, py = normalize_coordinates([px, py], shot)
#                     return [px - 12, py - 12, 24, 24]

#         except Exception as e:
#             logger.debug("detection adapter error: %s", e, exc_info=True)

#         return None


#     # ====================================================================
#     # DECISION: click / type / enter
#     # ====================================================================
#     def _decide_event(self, description: str) -> Dict[str, Any]:
#         import re

#         desc = description.strip()
#         ldesc = desc.lower()

#         # -----------------------------------------------------------
#         # TYPE WITH QUOTED TEXT  → type with payload
#         # -----------------------------------------------------------
#         m = re.search(r"type\s+['\"]([^'\"]+)['\"]", description, re.IGNORECASE)
#         if m:
#             return {"event": "type", "text": m.group(1)}

#         # -----------------------------------------------------------
#         # TYPE ANYTHING INSIDE QUOTES (fallback)
#         # -----------------------------------------------------------
#         m2 = re.search(r"['\"]([^'\"]+)['\"]", description)
#         if "type" in ldesc and m2:
#             return {"event": "type", "text": m2.group(1)}

#         # -----------------------------------------------------------
#         # PRESS ENTER
#         # -----------------------------------------------------------
#         if "press enter" in ldesc or ldesc == "enter":
#             return {"event": "keypress", "key": "enter"}

#         # -----------------------------------------------------------
#         # BACKSPACE
#         # -----------------------------------------------------------
#         if "backspace" in ldesc:
#             return {"event": "keypress", "key": "backspace"}

#         # -----------------------------------------------------------
#         # DELETE
#         # -----------------------------------------------------------
#         if "delete" in ldesc and "backspace" not in ldesc:
#             return {"event": "keypress", "key": "delete"}

#         # -----------------------------------------------------------
#         # SELECT ALL (CTRL+A)
#         # -----------------------------------------------------------
#         if "select all" in ldesc or "ctrl+a" in ldesc:
#             return {"event": "hotkey", "keys": ["ctrl", "a"]}

#         # -----------------------------------------------------------
#         # PASTE (CTRL+V)
#         # -----------------------------------------------------------
#         if "paste" in ldesc or "ctrl+v" in ldesc:
#             return {"event": "hotkey", "keys": ["ctrl", "v"]}

#         # -----------------------------------------------------------
#         # ARROW KEYS
#         # -----------------------------------------------------------
#         if "arrow left" in ldesc:
#             return {"event": "keypress", "key": "left"}

#         if "arrow right" in ldesc:
#             return {"event": "keypress", "key": "right"}

#         if "arrow up" in ldesc:
#             return {"event": "keypress", "key": "up"}

#         if "arrow down" in ldesc:
#             return {"event": "keypress", "key": "down"}

#         # -----------------------------------------------------------
#         # SCROLL
#         # -----------------------------------------------------------
#         if "scroll down" in ldesc:
#             return {"event": "scroll", "direction": "down"}

#         if "scroll up" in ldesc:
#             return {"event": "scroll", "direction": "up"}

#         # -----------------------------------------------------------
#         # CLICK AT SPECIFIC COORDINATES
#         # Example: "click at 200, 400"
#         # -----------------------------------------------------------
#         mcoord = re.search(r"click\s+at\s+(\d+)[,\s]+(\d+)", ldesc)
#         if mcoord:
#             x = int(mcoord.group(1))
#             y = int(mcoord.group(2))
#             return {"event": "click_at", "coords": (x, y)}

#         # -----------------------------------------------------------
#         # DOUBLE CLICK
#         # -----------------------------------------------------------
#         if "double click" in ldesc:
#             return {"event": "double_click"}

#         # -----------------------------------------------------------
#         # RIGHT CLICK
#         # -----------------------------------------------------------
#         if "right click" in ldesc or "context" in ldesc:
#             return {"event": "right_click"}

#         # -----------------------------------------------------------
#         # FALLBACK → NORMAL CLICK
#         # -----------------------------------------------------------
#         if "click" in ldesc:
#             return {"event": "click"}

#         # -----------------------------------------------------------
#         # FINAL FALLBACK → type raw text
#         # -----------------------------------------------------------
#         return {"event": "type", "text": description}



#     # ====================================================================
#     # SAFE CLICK
#     # ====================================================================
#     def _safe_click_xy(self, x: int, y: int):
#         jitter = random.randint(-2, 2)
#         try:
#             pyautogui.moveTo(x + jitter, y + jitter, duration=0.12)
#             pyautogui.click()
#         except Exception as e:
#             logger.debug("pyautogui click error: %s", e)


#     # ====================================================================
#     # PERFORM ACTION
#     # ====================================================================
#     def _perform(self, bbox: List[int], decision: Dict[str, Any]) -> Dict[str, Any]:
#         before = _screenshot(self.output_dir, "before")

#         x = int(bbox[0] + bbox[2] / 2)
#         y = int(bbox[1] + bbox[3] / 2)

#         try:
#             event = decision.get("event")

#             # CLICK
#             if event == "click":
#                 self._safe_click_xy(x, y)

#             # CLICK AT COORDINATES
#             elif event == "click_at":
#                 cx, cy = decision["coords"]
#                 self._safe_click_xy(cx, cy)

#             # DOUBLE CLICK
#             elif event == "double_click":
#                 self._safe_click_xy(x, y)
#                 time.sleep(0.05)
#                 self._safe_click_xy(x, y)

#             # RIGHT CLICK
#             elif event == "right_click":
#                 pyautogui.moveTo(x, y)
#                 pyautogui.rightClick()

#             # TYPE TEXT
#             elif event == "type":
#                 pyautogui.moveTo(x, y)
#                 pyautogui.click()
#                 text = decision.get("text")
#                 if text:
#                     pyautogui.write(text, interval=0.01)
#                 else:
#                     pyautogui.press("enter")

#             # KEYPRESS
#             elif event == "keypress":
#                 key = decision["key"]
#                 pyautogui.press(key)

#             # HOTKEY (like ctrl+a, ctrl+v)
#             elif event == "hotkey":
#                 keys = decision["keys"]
#                 pyautogui.hotkey(*keys)

#             # SCROLL
#             elif event == "scroll":
#                 direction = decision["direction"]
#                 pyautogui.moveTo(x, y)
#                 pyautogui.scroll(300 if direction == "up" else -300)

#             else:
#                 raise ValueError(f"Unknown event: {event}")

#             time.sleep(0.5)

#         except Exception as e:
#             after = _screenshot(self.output_dir, "after")
#             return {"status": "failed", "before": before, "after": after, "error": str(e)}

#         after = _screenshot(self.output_dir, "after")
#         # include bbox & decision so validator can inspect region diffs
#         return {"status": "success", "before": before, "after": after, "bbox": bbox, "decision": decision}



#     # ====================================================================
#     # MAIN YAML EXECUTOR
#     # ====================================================================
#     def run_step_yaml(self, step_yaml: str, validator_agent, max_attempts: int = 3) -> str:

#         step = yaml.safe_load(step_yaml)
#         description = step.get("description")
#         step_id = step.get("step_id")

#         # -------------------------------------------------------
#         # SYSTEM ACTION: OPEN BROWSER
#         # -------------------------------------------------------
#         low = (description or "").lower().strip()
#         if low in ("open browser", "open the browser") or \
#            "open chrome" in low or "open google chrome" in low:

#             try:
#                 import platform, subprocess, webbrowser
#                 system = platform.system()

#                 # Linux
#                 if system == "Linux":
#                     commands = [
#                         ["google-chrome-stable", "--new-window", "https://google.com"],
#                         ["google-chrome", "--new-window", "https://google.com"],
#                         ["chrome", "--new-window", "https://google.com"],
#                         ["chromium-browser", "--new-window", "https://google.com"],
#                         ["chromium", "--new-window", "https://google.com"],
#                     ]
#                     launched = False
#                     for cmd in commands:
#                         try:
#                             subprocess.Popen(cmd)
#                             launched = True
#                             break
#                         except:
#                             continue
#                     if not launched:
#                         subprocess.Popen(["xdg-open", "https://google.com"])

#                 # macOS
#                 elif system == "Darwin":
#                     subprocess.Popen([
#                         "open", "-n", "-a", "Google Chrome",
#                         "--args", "--new-window", "https://google.com"
#                     ])

#                 # Windows
#                 elif system.startswith("Win"):
#                     try:
#                         subprocess.Popen([
#                             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
#                             "--new-window", "https://google.com"
#                         ])
#                     except:
#                         os.startfile("chrome")

#                 # fallback
#                 else:
#                     webbrowser.open("https://google.com", new=1)

#                 # Stabilize Chrome UI
#                 self._stabilize_chrome()

#                 before = _screenshot(self.output_dir, "before")
#                 after = _screenshot(self.output_dir, "after")

#                 return yaml.safe_dump({
#                     "execution": {"attempts": 1, "last": {"status": "success", "before": before, "after": after}},
#                     "validation": {"validation_status": "pass"},
#                     "escalate": False
#                 }, sort_keys=False)

#             except Exception as e:
#                 return yaml.safe_dump({
#                     "execution": {"attempts": 1, "last": {"error": str(e)}},
#                     "validation": {"validation_status": "fail"},
#                     "escalate": True
#                 }, sort_keys=False)


#         # ====================================================================
#         # NORMAL (NON-SYSTEM) EXECUTION LOOP
#         # ====================================================================
#         attempt = 0
#         last_execution = None
#         last_validation = None

#         while attempt < max_attempts:
#             attempt += 1
#             logger.info("Executor attempt %d for step %s: %s",
#                         attempt, step_id, description)

#             shot = _screenshot(self.output_dir, "shot")
#             bbox = self._detect_bbox(description, image_path=shot)

#             if not bbox:
#                 # Do NOT guess — return a no_bbox status so the orchestrator/validator can handle replan/escalation.
#                 before = _screenshot(self.output_dir, "before")
#                 after = _screenshot(self.output_dir, "after")
#                 exec_result = {"status": "no_bbox", "before": before, "after": after, "bbox": None}
#             else:
#                 decision = self._decide_event(description)
#                 exec_result = {**self._perform(bbox, decision)}

#             exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
#             validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
#             validation = yaml.safe_load(validation_yaml)

#             last_execution = exec_result
#             last_validation = validation

#             if validation.get("validation_status") == "pass":
#                 return yaml.safe_dump({
#                     "execution": {"attempts": attempt, "last": last_execution},
#                     "validation": validation,
#                     "escalate": False
#                 }, sort_keys=False)

#             # If validator says fail and attempt < max_attempts, loop to retry
#             logger.info("Validation failed for step %s (attempt %d). Details: %s", step_id, attempt, validation)
#             time.sleep(0.6)

#         return yaml.safe_dump({
#             "execution": {"attempts": attempt, "last": last_execution},
#             "validation": last_validation,
#             "escalate": True,
#             "escalation_reason": "max_attempts_reached"
#         }, sort_keys=False)


#     # ====================================================================
#     # BACKWARDS COMPATIBILITY FOR ORCHESTRATOR
#     # ====================================================================
#     def run_step(self, step_description: str, validator_agent, max_attempts: int = 3) -> Dict[str, Any]:
#         step_payload = {"step_id": 0, "description": step_description}
#         step_yaml = yaml.safe_dump(step_payload, sort_keys=False)
#         result_yaml = self.run_step_yaml(step_yaml, validator_agent, max_attempts)
#         try:
#             return yaml.safe_load(result_yaml)
#         except:
#             return {
#                 "execution": {"attempts": 0, "last": None},
#                 "validation": {"validation_status": "unknown"},
#                 "escalate": True
#             }
