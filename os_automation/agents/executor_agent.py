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
import sys
import time
import uuid
import json
import subprocess
import logging
import platform
from typing import Optional, List, Dict, Any, Tuple

from PIL import Image
import pyautogui
import webbrowser
import random


from os_automation.core.registry import registry
from os_automation.repos.osatlas_adapter import _parse_position_raw, normalize_coordinates, draw_big_dot

logger = logging.getLogger(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")


class ExecutorAgent:
    """
    Executor agent with:
      - System-level action handling (open browser, open terminal, open folder).
      - Hybrid detection: prefer configured detection adapter, fallback to repeated locate.
      - Event decision via heuristics or LLM.
      - Jitter-safe pyautogui execution.
    """

    def __init__(self, default_detection="osatlas", default_executor="pyautogui", openai_model="gpt-4", chrome_preference=True):
        self.default_detection = default_detection
        self.default_executor = default_executor
        self.openai_model = openai_model
        self.OPENAI_KEY = OPENAI_KEY
        self.chrome_preference = chrome_preference  # if True, try to launch Chrome when "open browser"
        self.output_dir = os.path.join(os.getcwd(), "os_automation_output")
        os.makedirs(self.output_dir, exist_ok=True)
        # pyautogui safety
        pyautogui.FAILSAFE = True

    # -------------------------
    # Screenshots
    # -------------------------
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
            Image.new("RGB", (800, 600), (255, 255, 255)).save(path)
            return path

    # -------------------------
    # System-level actions
    # -------------------------
    def _launch_chrome(self) -> str:
        """
        Try several common chrome binaries on Linux, macOS, Windows.
        Falls back to webbrowser.open('about:blank') or xdg-open.
        """
        try:
            system = platform.system()
            if system == "Linux":
                # common variants
                candidates = ["google-chrome-stable", "google-chrome", "chrome", "chromium", "chromium-browser"]
                for cmd in candidates:
                    try:
                        subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        logger.info("Launched chrome binary: %s", cmd)
                        return "launched_chrome"
                    except Exception:
                        continue
                # fallback: open a URL with xdg-open (will use default browser)
                try:
                    subprocess.Popen(["xdg-open", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return "launched_via_xdg_open"
                except Exception:
                    pass
            elif system == "Darwin":
                try:
                    subprocess.Popen(["open", "-a", "Google Chrome"])
                    return "launched_chrome_mac"
                except Exception:
                    pass
            elif system.startswith("Win") or system == "Windows":
                try:
                    os.startfile("chrome")
                    return "launched_chrome_win"
                except Exception:
                    pass
            # final fallback: use webbrowser (may open default browser)
            webbrowser.open("about:blank", new=1)
            return "launched_webbrowser_fallback"
        except Exception as e:
            logger.exception("Chrome launch failed: %s", e)
            return f"error:{e}"

    def _open_default_browser_to_url(self, url: str) -> str:
        try:
            system = platform.system()
            if system == "Linux":
                try:
                    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return "xdg-open"
                except Exception:
                    pass
            elif system == "Darwin":
                try:
                    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return "open_mac"
                except Exception:
                    pass
            elif system.startswith("Win") or system == "Windows":
                try:
                    os.startfile(url)
                    return "start_win"
                except Exception:
                    pass
            webbrowser.open(url, new=1)
            return "webbrowser_open"
        except Exception as e:
            logger.exception("Open URL failed: %s", e)
            return f"error:{e}"

    def _open_terminal(self) -> str:
        try:
            system = platform.system()
            home = os.path.expanduser("~")
            if system == "Linux":
                for cmd in (["gnome-terminal"], ["konsole"], ["x-terminal-emulator"], ["xterm"]):
                    try:
                        subprocess.Popen(cmd, cwd=home)
                        return "opened_terminal_linux"
                    except Exception:
                        continue
            elif system == "Darwin":
                subprocess.Popen(["open", "-a", "Terminal"], cwd=home)
                return "opened_terminal_mac"
            elif system.startswith("Win") or system == "Windows":
                subprocess.Popen(["cmd.exe"], cwd=home)
                return "opened_terminal_win"
        except Exception as e:
            logger.exception("Open terminal failed: %s", e)
            return f"error:{e}"
        return "no_terminal_found"

    def _open_folder(self, path: str) -> str:
        try:
            expanded = os.path.expanduser(path or "~")
            if not os.path.exists(expanded):
                return f"not_found:{expanded}"
            system = platform.system()
            if system == "Linux":
                subprocess.Popen(["xdg-open", expanded])
            elif system == "Darwin":
                subprocess.Popen(["open", expanded])
            elif system.startswith("Win") or system == "Windows":
                os.startfile(expanded)
            return f"opened:{expanded}"
        except Exception as e:
            logger.exception("Open folder failed: %s", e)
            return f"error:{e}"

    def _execute_system_action(self, step_description: str) -> Optional[Dict[str, Any]]:
        """
        If the step is a system action (open browser/terminal/folder), execute and return a simple exec result.
        Otherwise return None to indicate normal UI path.
        """
        desc = step_description.lower().strip()

        # open browser / chrome
        if desc in ("open browser", "open the browser") or "open chrome" in desc or "open google chrome" in desc:
            if self.chrome_preference:
                res = self._launch_chrome()
            else:
                res = self._open_default_browser_to_url("http://www.google.com")

            # NEW — Auto-handle Chrome profile screen & popups
            self._post_launch_chrome_cleanup()

            before = self._screenshot("before")
            time.sleep(0.6)
            after = self._screenshot("after")
            return {"status": "success", "before": before, "after": after, "system": res}


        # open url directly
        if desc.startswith("open url") or desc.startswith("open "):
            # parse url after 'open '
            m = None
            import re
            m = re.search(r"open (https?://[^\s]+|[\w\-]+\.[a-zA-Z]{2,})", desc)
            if m:
                url = m.group(1)
                res = self._open_default_browser_to_url(url if url.startswith("http") else f"http://{url}")
                time.sleep(1.2)
                before = self._screenshot("before")
                time.sleep(0.6)
                after = self._screenshot("after")
                return {"status": "success", "before": before, "after": after, "system": res}

        # open terminal
        if "open terminal" in desc:
            res = self._open_terminal()
            time.sleep(0.8)
            before = self._screenshot("before")
            time.sleep(0.6)
            after = self._screenshot("after")
            return {"status": "success", "before": before, "after": after, "system": res}

        # open folder
        if desc.startswith("open folder") or desc.startswith("open ") and ("folder" in desc or "explorer" in desc):
            # try to extract a path
            import re
            m = re.search(r"open folder (.+)", desc)
            path = m.group(1) if m else None
            res = self._open_folder(path)
            time.sleep(0.6)
            before = self._screenshot("before")
            time.sleep(0.6)
            after = self._screenshot("after")
            return {"status": "success", "before": before, "after": after, "system": res}

        return None

    # -------------------------
    # Detection & fallback locate (OC-style)
    # -------------------------
    def detect_bbox_for_step(self, step_description: str, image_path: Optional[str] = None, tries: int = 3) -> Optional[List[int]]:
        """
        Prefer adapter detection (adapter.detect or adapter.call). Normalize to [x,y,w,h].
        """
        det_factory = registry.get_adapter(self.default_detection)
        if det_factory is None:
            logger.warning("No detection adapter registered: %s", self.default_detection)
            return None
        det = det_factory() if callable(det_factory) else det_factory

        shot = image_path or self._screenshot("shot")
        payload = {"image_path": shot, "text": step_description}
        try:
            res = None
            for fn in ("detect", "run", "predict", "infer", "call"):
                try:
                    if hasattr(det, fn):
                        res = getattr(det, fn)(payload)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Detection adapter call error: %s", e)
            res = None

        # Normalise result to [x,y,w,h]
        if res:
            if isinstance(res, dict) and "bbox" in res:
                bx = res["bbox"]
                try:
                    if len(bx) >= 4:
                        x, y, w, h = bx[0], bx[1], bx[2], bx[3]
                        # convert x1,y1,x2,y2
                        if x >= 0 and y >= 0 and (w > 1000 or h > 1000 or bx[2] > bx[0]):
                            x1, y1, x2, y2 = bx[:4]
                            cx = int((x1 + x2) / 2)
                            cy = int((y1 + y2) / 2)
                            w = int(abs(x2 - x1))
                            h = int(abs(y2 - y1))
                            x = cx - w // 2
                            y = cy - h // 2
                        return [int(x), int(y), int(w), int(h)]
                except Exception:
                    logger.debug("Invalid bbox format from adapter: %s", bx)
            # point-like responses
            if isinstance(res, (list, tuple)) and len(res) >= 2:
                parsed = _parse_position_raw(res)
                if parsed:
                    nx, ny = normalize_coordinates(parsed, shot)
                    return [nx - 10, ny - 10, 20, 20]
            if isinstance(res, dict) and "point" in res:
                parsed = _parse_position_raw(res["point"])
                if parsed:
                    nx, ny = normalize_coordinates(parsed, shot)
                    return [nx - 10, ny - 10, 20, 20]

        return None

    def _locate_target_fallback(self, query: str, tries: int = 4, delay: float = 0.5) -> Optional[Tuple[int, int]]:
        """
        OC-style locate: repeatedly screenshot and call grounding model until a coordinate is found.
        Returns (x,y) or None.
        """
        det_factory = registry.get_adapter(self.default_detection)
        if det_factory is None:
            return None
        det = det_factory() if callable(det_factory) else det_factory

        for attempt in range(tries):
            shot = self._screenshot("shot")
            pos_raw = None
            try:
                # try multiple call styles
                try:
                    pos_raw = det.call(query, shot)
                except Exception:
                    try:
                        pos_raw = det({"image_path": shot, "text": query})
                    except Exception:
                        try:
                            pos_raw = det.detect({"image_path": shot, "text": query})
                        except Exception:
                            pos_raw = None
                parsed = _parse_position_raw(pos_raw) if pos_raw is not None else None
                if parsed:
                    nx, ny = normalize_coordinates(parsed, shot)
                    if nx < 50 and ny < 50:  # deadzone avoidance
                        nx += 80
                        ny += 80
                    return int(nx), int(ny)
            except Exception as e:
                logger.debug("Fallback locate attempt error: %s", e)
            time.sleep(delay)
        return None

    # -------------------------
    # Decide event
    # -------------------------
    def decide_event_with_llm(self, step_description: str, bbox: List[int]) -> Dict[str, Any]:
        """
        Heuristic decision or use OpenAI to return JSON {"event":..., "text":...}
        """
        heuristic = {"event": "click", "text": None}
        lower = step_description.lower()
        if "type" in lower or "enter" in lower or "search" in lower or "'" in step_description or '"' in step_description:
            import re
            m = re.search(r"['\"](.+?)['\"]", step_description)
            heuristic = {"event": "type", "text": m.group(1) if m else None}
        if "double" in lower:
            heuristic["event"] = "double_click"
        if "right click" in lower or "context" in lower:
            heuristic["event"] = "right_click"
        if "scroll" in lower:
            heuristic["event"] = "scroll"
        if "press enter" in lower or step_description.strip().lower() == "press enter" or step_description.strip().lower() == "press return":
            heuristic = {"event": "type", "text": None}

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
                messages=[{"role": "user", "content": prompt}],
                max_tokens=128,
                temperature=0.0,
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[-2].strip()
            if "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            parsed = json.loads(content)
            return {"event": parsed.get("event"), "text": parsed.get("text")}
        except Exception as e:
            logger.debug("LLM decision failed: %s", e)
            return heuristic

    # -------------------------
    # Perform action
    # -------------------------

    def _safe_click_xy(self, x: int, y: int, repeats: int = 2, delay: float = 0.08):
        """Jitter-safe click with real random library."""
        for _ in range(repeats):
            jitter_x = random.randint(-2, 2)
            jitter_y = random.randint(-2, 2)
            try:
                pyautogui.moveTo(x + jitter_x, y + jitter_y, duration=0.12)
                pyautogui.click()
            except Exception as e:
                logger.debug("pyautogui click error: %s", e)
            time.sleep(delay)


    def _perform_action(self, bbox: List[int], event: str, text: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute using pyautogui. Returns dict: status, before, after, bbox, error(optional).
        """
        before = self._screenshot("before")
        x = int(bbox[0] + bbox[2] / 2)
        y = int(bbox[1] + bbox[3] / 2)

        try:
            # move and action
            self._safe_click_xy(x, y, repeats=1, delay=0.06)  # move into position
            time.sleep(0.06)
            if event == "click":
                self._safe_click_xy(x, y)
            elif event == "double_click":
                self._safe_click_xy(x, y)
                time.sleep(0.06)
                self._safe_click_xy(x, y)
            elif event == "right_click":
                try:
                    pyautogui.rightClick()
                except Exception:
                    # fallback: click then context menu key
                    pyautogui.click()
            elif event == "type":
                if text is not None:
                    # ensure focus
                    pyautogui.click()
                    time.sleep(0.05)
                    pyautogui.write(str(text), interval=0.01)
                else:
                    # if no text, try pressing enter
                    pyautogui.press("enter")
            elif event == "scroll":
                pyautogui.scroll(-300)
            elif event == "noop":
                pass
            else:
                pyautogui.click()
        except Exception as e:
            logger.exception("Execution error: %s", e)
            after = self._screenshot("after")
            return {"status": "failed", "before": before, "after": after, "error": str(e)}

        # allow UI to settle
        time.sleep(0.8)
        after = self._screenshot("after")
        return {"status": "success", "before": before, "after": after}

    # -------------------------
    # High-level per-step runner
    # -------------------------
    def run_step(self, step_description: str, validator_agent, max_attempts: int = 3) -> Dict[str, Any]:
        """
        Top-level: if step is system-level (open browser/terminal/folder) -> run system action.
        Otherwise: detect bbox (adapter -> fallback locate), decide event, execute, validate.
        Retries up to max_attempts.
        """
        # 0) System actions bypass detection
        system_result = self._execute_system_action(step_description)
        if system_result is not None:
            # If system_result was executed, run validation quickly
            validation = validator_agent.validate_step({"description": step_description}, {
                "before": system_result.get("before"),
                "after": system_result.get("after"),
                "raw": {"system": system_result.get("system")}
            })
            exec_out = {"status": system_result.get("status", "success"),
                        "before": system_result.get("before"),
                        "after": system_result.get("after"),
                        "bbox": None,
                        "decision": {"event": "system", "text": None}}
            return {"execution": exec_out, "validation": validation}

        attempt = 0
        final_exec = None
        final_validation = None

        while attempt < max_attempts:
            attempt += 1
            logger.info("Attempt %d for step: %s", attempt, step_description)

            # screenshot for detection
            shot = self._screenshot("shot")
            bbox = self.detect_bbox_for_step(step_description, image_path=shot, tries=1)

            # fallback to locate if adapter failed
            if not bbox:
                logger.debug("Primary detection failed; trying fallback locate.")
                pt = self._locate_target_fallback(step_description, tries=3, delay=0.6)
                if pt:
                    nx, ny = pt
                    bbox = [nx - 10, ny - 10, 20, 20]
                else:
                    logger.info("No bbox found for step '%s' on attempt %d", step_description, attempt)
                    # still take a before/after to allow validator to detect change (some steps are keypresses)
                    time.sleep(0.4)
                    continue

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

            # backoff before retry
            time.sleep(0.5)

        return {"execution": final_exec, "validation": final_validation}


    def _post_launch_chrome_cleanup(self):
        """
        After Chrome opens:
        - Detect profile picker
        - Auto-click Guest Mode or first profile
        - Auto-close popups
        - Ensure Google.com is opened
        """
        time.sleep(1.5)

        # Take a screenshot for detection
        shot = self._screenshot("chrome_start")

        # Try detecting text using your detection adapter (OSAtlas or Omniparser)
        det_factory = registry.get_adapter(self.default_detection)
        det = det_factory() if callable(det_factory) else det_factory

        def click_if_found(label_query: str, tries=3):
            """Search a label and click the detected bbox."""
            for _ in range(tries):
                try:
                    shot2 = self._screenshot("detect")
                    bbox = None

                    # Try all detection call styles
                    try:
                        res = det.call(label_query, shot2)
                    except Exception:
                        try:
                            res = det({"image_path": shot2, "text": label_query})
                        except:
                            try:
                                res = det.detect({"image_path": shot2, "text": label_query})
                            except:
                                res = None

                    parsed = _parse_position_raw(res) if res else None
                    if not parsed:
                        time.sleep(0.4)
                        continue

                    x, y = normalize_coordinates(parsed, shot2)
                    self._safe_click_xy(x, y, repeats=2)
                    return True
                except Exception:
                    time.sleep(0.4)
            return False

        # ---- 1. Click Guest mode (if visible) ----
        if click_if_found("Guest"):
            time.sleep(1)
        else:
            # ---- 2. Click first visible profile (e.g. your name) ----
            click_if_found("V", tries=3)  # For Vedanshi
            click_if_found("p", tries=3)  # For pyemptyops
            click_if_found("Add", tries=3)  # fallback

        time.sleep(1.2)

        # ---- 3. Close onboarding popups ----
        click_if_found("No thanks")
        click_if_found("Skip")
        click_if_found("Continue without syncing")

        # ---- 4. Force new tab ----
        try:
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.4)
        except:
            pass

        # ---- 5. Type google.com if nothing else visible ----
        try:
            pyautogui.typewrite("https://google.com", interval=0.04)
            pyautogui.press("enter")
        except:
            pass

        time.sleep(1)
