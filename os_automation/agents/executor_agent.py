# # os_automation/agents/executor_agent.py
# import os
# import time
# import uuid
# import yaml
# import logging
# import random
# import yaml
# from typing import Optional, Dict, Any, List

# from PIL import Image
# import pyautogui

# import platform, subprocess, webbrowser

# from os_automation.agents.validator_agent import ValidatorAgent


# from os_automation.core.registry import registry
# from os_automation.repos.osatlas_adapter import (
#     _parse_position_raw,
#     normalize_coordinates
# )

# logger = logging.getLogger(__name__)
# pyautogui.FAILSAFE = True

# # Default attempts: retry 3 times, on 4th -> replan
# DEFAULT_MAX_ATTEMPTS = 4


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
#         output_dir: str = None,
#         max_attempts: int = DEFAULT_MAX_ATTEMPTS
#     ):
        
#         self.validator = ValidatorAgent()

#         self.default_detection = default_detection
#         self.default_executor = default_executor
#         self.openai_model = openai_model
#         self.chrome_preference = chrome_preference

#         # Number of attempts before escalation/replan (default 4: 3 retries then replan)
#         self.max_attempts = int(max_attempts)

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
#     # DETECT BBOX
#     # ====================================================================
#     def _detect_bbox(self, description: str, image_path: Optional[str] = None) -> Optional[List[int]]:
        
        
#         # -----------------------------------------------------------
#         # LLM REWRITE: Convert description → ideal OSAtlas keyword
#         # -----------------------------------------------------------
#         try:
#             from os_automation.agents.main_ai import MainAIAgent
#             ma = MainAIAgent()

#             rewritten = ma.rewrite_ui_query(description)
#             if rewritten:
#                 description = rewritten

#         except Exception as e:
#             logger.debug(f"LLM rewrite failed: {e}")

        
#         # 🔥 Smart browser element text remapping for OSAtlas
#         alias = {
#             "click search box": "search",
#             "search box": "search",
#             "searchbar": "search",
#             "search bar": "search",
#             "google search": "search",
#             "click search": "search",
#             "click on search": "search",
#             "search field": "search",
#             "click address bar": "address bar",
#             "address bar": "address bar",
#             "url bar": "address bar",
#             "omnibox": "address bar",
#             "click url": "address bar",
#             "click on the youtube link": "YouTube",
#             "youtube link": "YouTube",
#             "first youtube link": "YouTube",
#             "vscode explorer": "Explorer",
#             "explorer icon": "Explorer",
#             "vscode sidebar": "Explorer",
#             "new file": "New File",
#             "new file button": "New File",
#             "file name": "File Name",
#             "file name field": "File Name",
#             "editor window": "Editor",
#             "side panel": "Explorer",
#         }

#         for k, v in alias.items():
#             if k in description.lower():
#                 description = v
#                 break

        
#         det = self._get_detection_adapter()
#         shot = image_path or _screenshot(self.output_dir, "shot")
        
#         if not det:
#             return None

#         try:
#             for fn in ("detect", "call", "run", "predict", "infer"):
#                 if hasattr(det, fn):
#                     try:
#                         # ==========================================================
#                         # 🔥 LLM-enhanced query normalization for OSAtlas
#                         # ==========================================================
#                         try:
#                             from os_automation.agents.main_ai import MainAIAgent
#                             ma = MainAIAgent()

#                             llm_target = ma.decide_event_llm(
#                                 description=description,
#                                 bbox=None,
#                                 image_path=shot
#                             )

#                             # if LLM provides focus target or query
#                             if isinstance(llm_target, dict):
#                                 if "focus_target" in llm_target:
#                                     description = llm_target["focus_target"]
#                                 elif "query" in llm_target:
#                                     description = llm_target["query"]

#                         except Exception as e:
#                             logger.debug("LLM target normalization failed: %s", e)

#                         res = getattr(det, fn)({"image_path": shot, "text": description})
#                         if isinstance(res, dict) and "bbox" in res:
#                             bx = res["bbox"]
#                             if len(bx) >= 4:
#                                 x, y, w, h = bx[:4]
#                                 if (w > 1000 or h > 1000) or (bx[2] > bx[0] and bx[3] > bx[1]):
#                                     x1, y1, x2, y2 = bx[:4]
#                                     w = abs(x2 - x1)
#                                     h = abs(y2 - y1)
#                                     x = min(x1, x2)
#                                     y = min(y1, y2)
#                                 return [int(x), int(y), int(max(1,w)), int(max(1,h))]

#                         # point detector
#                         if isinstance(res, (list, tuple)) and len(res) >= 2:
#                             parsed = _parse_position_raw(res)
#                             if parsed:
#                                 nx, ny = normalize_coordinates(parsed, shot)
#                                 return [nx - 10, ny - 10, 20, 20]

#                     except Exception as inner_e:
#                         logger.debug("inner detection error: %s", inner_e)

#         except Exception as e:
#             logger.debug("detection adapter error: %s", e)

#         return None


    
#     # ====================================================================
#     # DECISION: Fully patched event mapping (supports 15+ actions)
#     # ====================================================================
#     def _decide_event(self, description: str) -> Dict[str, Any]:
#         import re

#         desc = description.strip().lower()

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
#         if "type" in desc and m2:
#             return {"event": "type", "text": m2.group(1)}

#         # -----------------------------------------------------------
#         # PRESS ENTER
#         # -----------------------------------------------------------
#         if "press enter" in desc or desc == "enter":
#             return {"event": "keypress", "key": "enter"}

#         # -----------------------------------------------------------
#         # BACKSPACE
#         # -----------------------------------------------------------
#         if "backspace" in desc:
#             return {"event": "keypress", "key": "backspace"}

#         # -----------------------------------------------------------
#         # DELETE
#         # -----------------------------------------------------------
#         if "delete" in desc and "backspace" not in desc:
#             return {"event": "keypress", "key": "delete"}

#         # -----------------------------------------------------------
#         # SELECT ALL (CTRL+A)
#         # -----------------------------------------------------------
#         if "select all" in desc or "ctrl+a" in desc:
#             return {"event": "hotkey", "keys": ["ctrl", "a"]}

#         # -----------------------------------------------------------
#         # PASTE (CTRL+V)
#         # -----------------------------------------------------------
#         if "paste" in desc or "ctrl+v" in desc:
#             return {"event": "hotkey", "keys": ["ctrl", "v"]}

#         # -----------------------------------------------------------
#         # ARROW KEYS
#         # -----------------------------------------------------------
#         if "arrow left" in desc:
#             return {"event": "keypress", "key": "left"}

#         if "arrow right" in desc:
#             return {"event": "keypress", "key": "right"}

#         if "arrow up" in desc:
#             return {"event": "keypress", "key": "up"}

#         if "arrow down" in desc:
#             return {"event": "keypress", "key": "down"}

#         # -----------------------------------------------------------
#         # SCROLL
#         # -----------------------------------------------------------
#         if "scroll down" in desc:
#             return {"event": "scroll", "direction": "down"}

#         if "scroll up" in desc:
#             return {"event": "scroll", "direction": "up"}

#         # -----------------------------------------------------------
#         # CLICK AT SPECIFIC COORDINATES
#         # Example: "click at 200, 400"
#         # -----------------------------------------------------------
#         mcoord = re.search(r"click\s+at\s+(\d+)[,\s]+(\d+)", desc)
#         if mcoord:
#             x = int(mcoord.group(1))
#             y = int(mcoord.group(2))
#             return {"event": "click_at", "coords": (x, y)}

#         # -----------------------------------------------------------
#         # DOUBLE CLICK
#         # -----------------------------------------------------------
#         if "double click" in desc:
#             return {"event": "double_click"}

#         # -----------------------------------------------------------
#         # RIGHT CLICK
#         # -----------------------------------------------------------
#         if "right click" in desc or "context" in desc:
#             return {"event": "right_click"}

#         # -----------------------------------------------------------
#         # FALLBACK → NORMAL CLICK
#         # -----------------------------------------------------------
#         # 🔥 SPECIAL CASE — GOOGLE SEARCH FIELD
#         if desc in ("click search box", "search box", "click search", "search"):
#             return {"event": "click_google_search"}
        
#         # -----------------------------------------------------------
#         # WAIT / NO-OP
#         # -----------------------------------------------------------
#         # near other fallbacks
#         if "wait" in desc or "pause" in desc or desc in ("noop", "no-op"):
#             return {"event": "noop"}


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
            
#             if decision.get("event") == "click_google_search":
#                 width, height = pyautogui.size()
#                 x = width // 2
#                 y = int(height * 0.40)   # consistent click on Google search field
#                 self._safe_click_xy(x, y)
#                 time.sleep(0.7)
#                 after = _screenshot(self.output_dir, "after")
#                 return {"status": "success", "before": before, "after": after}

            
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
                
#             # NO-OP / WAIT
#             elif event == "noop":
#                 time.sleep(1)


#             else:
#                 raise ValueError(f"Unknown event: {event}")

#             time.sleep(0.5)

#         except Exception as e:
#             after = _screenshot(self.output_dir, "after")
#             return {"status": "failed", "before": before, "after": after, "error": str(e)}

#         after = _screenshot(self.output_dir, "after")
#         return {"status": "success", "before": before, "after": after}


#     # ----------------------------------------------------------------
#     # NEW: YAML-driven action executor (uses OSAtlas for detection, PyAutoGUI adapter for events)
#     # ----------------------------------------------------------------
#     def run_action_yaml(self, action_yaml: str, validator_agent, original_prompt: str = "", max_attempts: int = None) -> str:
#         """
#         Input YAML (string):
#         execute:
#           description: "click the save button"
#           action:
#             type: "query_click" | "click_at" | "type" | "run_command" | "open_terminal" | ...
#             query: "Save"
#             coords: [x,y]
#             text: "hello"
#             command: "ls -la"

#         Behavior:
#           - For actions that require bbox (query_click) -> use detection adapter (OSAtlas)
#           - For event execution -> prefer adapter.execute (pyautogui adapter) if available
#           - Validate using validator_agent.validate_step_yaml (expects YAML)
#           - Retry up to (max_attempts - 1) times; on final failure (attempt == max_attempts) call MainAIAgent.replan_on_failure(...) and return replan YAML
#         """
#         import json
#         from os_automation.core.registry import registry
#         from os_automation.agents.main_ai import MainAIAgent

#         max_attempts = max_attempts or self.max_attempts

#         try:
#             payload = yaml.safe_load(action_yaml) or {}
#         except Exception as e:
#             # malformed YAML
#             return yaml.safe_dump({
#                 "execution": {"status": "failed", "error": "malformed_action_yaml", "message": str(e)},
#                 "validation": {"validation_status": "fail"},
#                 "escalate": True
#             }, sort_keys=False)

#         exec_block = payload.get("execute") or payload.get("action_request") or payload
#         description = exec_block.get("description", "")
#         action = exec_block.get("action", {}) or payload.get("action")

#         # pack a step structure for validator compatibility
#         step = {"step_id": exec_block.get("step_id", 0), "description": description}

#         # Get adapters (OSAtlas detection + PyAutoGUI executor)
#         try:
#             det_factory = registry.get_adapter(self.default_detection)
#             det_adapter = det_factory() if callable(det_factory) else det_factory
#         except Exception:
#             det_adapter = None

#         try:
#             exec_factory = registry.get_adapter(self.default_executor)
#             exec_adapter = exec_factory() if callable(exec_factory) else exec_factory
#         except Exception:
#             exec_adapter = None

#         last_execution = None
#         last_validation = None

#         # Attempts loop: On attempt == max_attempts we will trigger replan if still failing
#         for attempt in range(1, max_attempts + 1):
#             logger.info("ExecutorAction attempt %d for action: %s", attempt, action)

#             # 1) Acquire a fresh screenshot
#             shot = _screenshot(self.output_dir, "shot")

#             # 2) Determine bbox if needed
#             bbox = None
#             if action.get("type") in ("query_click",):
#                 # call detection adapter
#                 if det_adapter:
#                     try:
#                         # adapter's detect interface: accepts dict with image_path and text/description
#                         try:
#                             detect_res = det_adapter.detect({"image_path": shot, "text": action.get("query") or description})
#                         except Exception:
#                             # Some adapters expect (image_path, text)
#                             detect_res = det_adapter.detect(shot, action.get("query") or description)

#                         if isinstance(detect_res, dict) and "bbox" in detect_res and detect_res["bbox"]:
#                             bbox = detect_res["bbox"]
#                         else:
#                             # fall back to parsing any list/tuple
#                             if isinstance(detect_res, (list, tuple)) and len(detect_res) >= 2:
#                                 parsed = _parse_position_raw(detect_res)
#                                 if parsed:
#                                     nx, ny = normalize_coordinates(parsed, shot)
#                                     bbox = [nx - 12, ny - 12, 24, 24]
#                     except Exception as de:
#                         logger.debug("Detection adapter error: %s", de)

#                 # Last resort: center fallback
#                 if not bbox:
#                     try:
#                         from PIL import Image
#                         img = Image.open(shot)
#                         W, H = img.size
#                         cx, cy = W // 2, H // 2
#                         bbox = [max(0, cx - 50), max(0, cy - 50), 100, 100]
#                         logger.warning("Query_click: falling back to center bbox for action=%s", action)
#                     except Exception:
#                         bbox = None

#             # 3) Build execution payload depending on action type
#             decision = None
#             event_type = None

#             if action.get("type") == "type":
#                 event_type = "type"
#                 decision = {"event": "type", "text": action.get("text")}

#             elif action.get("type") == "click_at":
#                 event_type = "click_at"
#                 coords = action.get("coords") or action.get("coords", [])
#                 if coords and len(coords) >= 2:
#                     decision = {"event": "click_at", "coords": (int(coords[0]), int(coords[1]))}
#                 else:
#                     decision = {"event": "click"}  # fallback

#             elif action.get("type") in ("query_click", "click"):
#                 event_type = "click"
#                 decision = {"event": "click"}

#             elif action.get("type") == "double_click":
#                 event_type = "double_click"
#                 decision = {"event": "double_click"}

#             elif action.get("type") == "right_click":
#                 event_type = "right_click"
#                 decision = {"event": "right_click"}

#             elif action.get("type") == "keypress":
#                 event_type = "keypress"
#                 decision = {"event": "keypress", "key": action.get("key", "enter")}

#             elif action.get("type") == "hotkey":
#                 event_type = "hotkey"
#                 decision = {"event": "hotkey", "keys": action.get("keys", ["ctrl", "v"])}

#             elif action.get("type") == "scroll":
#                 event_type = "scroll"
#                 decision = {"event": "scroll", "direction": action.get("direction", "down")}

#             elif action.get("type") == "run_command":
#                 # run system command synchronously (safer wrapper)
#                 cmd = action.get("command") or description
#                 try:
#                     import shlex, subprocess
#                     parts = shlex.split(cmd)
#                     proc = subprocess.Popen(parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
#                     out, err = proc.communicate(timeout=30)
#                     exec_result = {"status": "success" if proc.returncode == 0 else "failed", "stdout": out, "stderr": err, "before": shot, "after": _screenshot(self.output_dir, "after")}
#                 except Exception as e:
#                     exec_result = {"status": "failed", "error": str(e), "before": shot, "after": _screenshot(self.output_dir, "after")}

#                 # Validate
#                 # -------------------------------------------------------
#                 # VALIDATION PIPELINE (dual-phase: simple + advanced)
#                 # -------------------------------------------------------

#                 exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)

#                 # 1) OLD YAML validator
#                 yaml_validation = validator_agent.validate_step_yaml(exec_yaml)
#                 yaml_val_data = yaml.safe_load(yaml_validation)


#                 # 2) ADVANCED VALIDATION (pixel, OCR, region diff)
#                 adv_validation = validator_agent.validate_step_advanced(
#                     description=description,
#                     before_path=exec_result.get("before"),
#                     after_path=exec_result.get("after"),
#                     bbox=bbox or [0, 0, 80, 80]
#                 )

#                 # 3) SELECT THE SAFER / MORE CONFIDENT RESULT
#                 if adv_validation.get("valid"):
#                     validation = {
#                         "validation_status": "pass",
#                         "details": adv_validation
#                     }
#                 else:
#                     validation = {
#                         "validation_status": yaml_val_data.get("validation_status", "fail"),
#                         "details": yaml_val_data.get("details", {})
#                     }


#                 if validation.get("validation_status") == "pass":
#                     return yaml.safe_dump({"execution": {"attempts": attempt, "last": last_execution}, "validation": last_validation, "escalate": False}, sort_keys=False)
#                 else:
#                     # failed -> continue loop or escalate if last attempt
#                     if attempt >= max_attempts:
#                         # trigger replan (use safe original_prompt variable)
#                         failed_step_yaml = yaml.safe_dump({"step": step}, sort_keys=False)
#                         failure_details_yaml = yaml.safe_dump({"execution": last_execution, "validation": last_validation}, sort_keys=False)
#                         ma = MainAIAgent()
#                         # ensure original_prompt is safely referenced
#                         oprompt = original_prompt if ('original_prompt' in locals() and original_prompt) else description
#                         try:
#                             replan_yaml = ma.replan_on_failure(oprompt, failed_step_yaml, failure_details_yaml)
#                             replan_parsed = yaml.safe_load(replan_yaml)
#                         except Exception as e:
#                             replan_parsed = {"escalation": {"reason": "replan_failed_parse", "error": str(e), "raw": replan_yaml if 'replan_yaml' in locals() else None}}
#                         return yaml.safe_dump({
#                             "execution": {"attempts": attempt, "last": last_execution},
#                             "validation": last_validation,
#                             "escalate": True,
#                             "replan": replan_parsed
#                         }, sort_keys=False)

#                     else:
#                         time.sleep(0.6)
#                         continue

#             else:
#                 # default fallback -> treat as click
#                 decision = {"event": "click"}

#             # 4) Execute the decided event. Prefer adapter.execute if available.
#             exec_result = None
#             try:
#                 if exec_adapter and hasattr(exec_adapter, "execute"):
#                     # Build adapter step dict
#                     adapter_step = {
#                         "description": description,
#                         "action": action,
#                         "bbox": bbox,
#                         "decision": decision
#                     }
#                     try:
#                         adapter_result = exec_adapter.execute(adapter_step)
#                     except TypeError:
#                         # older adapters may expect different signature
#                         adapter_result = exec_adapter.execute(adapter_step)

#                     # normalize adapter_result to expected dict shape
#                     if isinstance(adapter_result, dict):
#                         exec_result = adapter_result
#                     else:
#                         exec_result = {"status": "success" if adapter_result else "failed", "raw": adapter_result, "before": shot, "after": _screenshot(self.output_dir, "after")}
#                 else:
#                     # use internal _perform -> requires bbox (fallback to tiny bbox if none)
#                     use_bbox = bbox or [10, 10, 80, 80]
#                     exec_result = {**self._perform(use_bbox, decision), "bbox": bbox, "decision": decision}
#             except Exception as e:
#                 exec_result = {"status": "failed", "error": str(e), "before": shot, "after": _screenshot(self.output_dir, "after")}

#             # 5) Validate
#             exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
#             validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
#             validation = yaml.safe_load(validation_yaml)

#             last_execution = exec_result
#             last_validation = validation

#             # If pass -> return success YAML
#             if validation.get("validation_status") == "pass":
#                 return yaml.safe_dump({
#                     "execution": {"attempts": attempt, "last": last_execution},
#                     "validation": validation,
#                     "escalate": False
#                 }, sort_keys=False)

#             # If failed and we've reached the max attempts -> trigger replan
#             logger.debug("Action attempt %d failed validation: %s", attempt, validation)
#             if attempt >= max_attempts:
#                 failed_step_yaml = yaml.safe_dump({"step": step}, sort_keys=False)
#                 failure_details_yaml = yaml.safe_dump({"execution": last_execution, "validation": last_validation}, sort_keys=False)
#                 ma = MainAIAgent()
#                 replan_yaml = ma.replan_on_failure(original_prompt or description, failed_step_yaml, failure_details_yaml)

#                 # return escalate + replan payload (as YAML structure)
#                 try:
#                     replan_parsed = yaml.safe_load(replan_yaml)
#                 except Exception:
#                     replan_parsed = {"escalation": {"reason": "replan_failed_parse", "raw": replan_yaml}}

#                 logger.warning("Action escalated to planner after %d attempts for: %s", attempt, description)
#                 return yaml.safe_dump({
#                     "execution": {"attempts": attempt, "last": last_execution},
#                     "validation": last_validation,
#                     "escalate": True,
#                     "replan": replan_parsed
#                 }, sort_keys=False)

#             # else -> wait and retry
#             time.sleep(0.6)

#         # Fallback final
#         return yaml.safe_dump({
#             "execution": {"attempts": max_attempts, "last": last_execution},
#             "validation": last_validation,
#             "escalate": True
#         }, sort_keys=False)



#     # ====================================================================
#     # MAIN YAML EXECUTOR
#     # ====================================================================
#     def run_step_yaml(self, step_yaml: str, validator_agent, max_attempts=None, original_prompt=None) -> str:

#         max_attempts = max_attempts or self.max_attempts

#         step = yaml.safe_load(step_yaml)
#         description = step.get("description")
#         step_id = step.get("step_id")

#         low = (description or "").lower().strip()

#         # -------------------------------------------------------
#         # SYSTEM ACTION: OPEN TERMINAL   (YAML in / YAML out)
#         # -------------------------------------------------------
#         if "open terminal" in low or low == "terminal":
#             try:
#                 system = platform.system()
#                 home = os.path.expanduser("~")

#                 # Linux
#                 if system == "Linux":
#                     # Try common terminal emulators
#                     for cmd in (["gnome-terminal"], ["konsole"], ["x-terminal-emulator"], ["xfce4-terminal"]):
#                         try:
#                             subprocess.Popen(cmd, cwd=home)
#                             break
#                         except Exception:
#                             continue
#                     else:
#                         # last resort
#                         subprocess.Popen(["xterm"], cwd=home)

#                 # macOS
#                 elif system == "Darwin":
#                     subprocess.Popen(["open", "-a", "Terminal"], cwd=home)

#                 # Windows
#                 elif system.startswith("Win"):
#                     subprocess.Popen(["cmd.exe"], cwd=home)

#                 # Take before/after screenshots for validator
#                 before = _screenshot(self.output_dir, "before")
#                 time.sleep(1.5)
#                 after = _screenshot(self.output_dir, "after")

#                 exec_result = {
#                     "status": "success",
#                     "before": before,
#                     "after": after
#                 }

#                 exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
#                 validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
#                 validation = yaml.safe_load(validation_yaml)

#                 return yaml.safe_dump({
#                     "execution": {"attempts": 1, "last": exec_result},
#                     "validation": validation,
#                     "escalate": validation.get("validation_status") != "pass"
#                 }, sort_keys=False)

#             except Exception as e:
#                 before = _screenshot(self.output_dir, "before")
#                 after = _screenshot(self.output_dir, "after")
#                 exec_result = {
#                     "status": "failed",
#                     "before": before,
#                     "after": after,
#                     "error": str(e)
#                 }
#                 exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
#                 validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
#                 validation = yaml.safe_load(validation_yaml)

#                 return yaml.safe_dump({
#                     "execution": {"attempts": 1, "last": exec_result},
#                     "validation": validation,
#                     "escalate": True
#                 }, sort_keys=False)
                
#         # -------------------------------------------------------
#         # SYSTEM ACTION: RUN COMMAND INSIDE TERMINAL
#         # -------------------------------------------------------
#         if low.startswith("run command"):
#             import re

#             # extract command text
#             m = re.search(r"run command ['\"](.+?)['\"]", low)
#             if not m:
#                 return yaml.safe_dump({
#                     "execution": {"attempts": 1, "last": {"status": "failed", "error": "malformed run command"}},
#                     "validation": {"validation_status": "fail"},
#                     "escalate": True
#                 }, sort_keys=False)

#             command = m.group(1)

#             attempt = 0
#             while attempt < max_attempts:
#                 attempt += 1

#                 before = _screenshot(self.output_dir, f"before_{step_id}")

#                 # Detect terminal via OSAtlas
#                 bbox = self._detect_bbox("terminal", image_path=before)

#                 if bbox:
#                     x, y, w, h = bbox
#                     cx = x + w // 2
#                     cy = y + h // 2

#                     pyautogui.moveTo(cx, cy)
#                     pyautogui.click()
#                     time.sleep(0.25)
#                     pyautogui.write(command, interval=0.015)
#                     pyautogui.press("enter")

#                 else:
#                     time.sleep(0.7)
#                     continue

#                 time.sleep(1.2)
#                 after = _screenshot(self.output_dir, f"after_{step_id}")

#                 exec_result = {"status": "success", "before": before, "after": after}

#                 exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
#                 validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
#                 validation = yaml.safe_load(validation_yaml)

#                 if validation.get("validation_status") == "pass":
#                     return yaml.safe_dump({
#                         "execution": {"attempts": attempt, "last": exec_result},
#                         "validation": validation,
#                         "escalate": False
#                     }, sort_keys=False)

#             return yaml.safe_dump({
#                 "execution": {"attempts": attempt, "last": exec_result},
#                 "validation": validation,
#                 "escalate": True
#             }, sort_keys=False)
        

#         # -------------------------------------------------------
#         # SYSTEM ACTION: OPEN BROWSER   (unchanged logic)
#         # -------------------------------------------------------
#         if low in ("open browser", "open the browser") or \
#            "open chrome" in low or "open google chrome" in low:

#             try:
#                 import webbrowser
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
#                         except Exception:
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
#                     except Exception:
#                         os.startfile("chrome")

#                 else:
#                     webbrowser.open("https://google.com", new=1)

#                 # Stabilize Chrome UI (maximize, focus address bar, etc.)
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
#                 before = _screenshot(self.output_dir, "before")
#                 logger.warning("No bbox found for step '%s' — falling back to press Enter (legacy behavior).", description)
#                 pyautogui.press("enter")
#                 time.sleep(0.6)
#                 after = _screenshot(self.output_dir, "after")
#                 exec_result = {"status": "no_bbox", "before": before, "after": after, "bbox": None}

#             else:
#                 # ----------------------------------------------------
#                 # 🔥 1) Ask LLM to choose BEST event for this bbox
#                 # ----------------------------------------------------
#                 llm_decision = None
#                 try:
#                     from os_automation.agents.main_ai import MainAIAgent
#                     ma = MainAIAgent()

#                     llm_decision = ma.decide_event_llm(
#                         description=description,
#                         bbox=bbox,
#                         image_path=shot
#                     )

#                 except Exception as e:
#                     logger.debug(f"LLM decision failed: {e}")
#                 # ----------------------------------------------------
#                 # 🔥 2) If LLM gives valid event → USE IT
#                 # ----------------------------------------------------
#                 if (
#                     isinstance(llm_decision, dict)
#                     and llm_decision.get("event")
#                     and llm_decision.get("event") != "unknown"
#                 ):
#                     decision = llm_decision

#                 else:
#                     # ------------------------------------------------
#                     # 🔥 3) fallback → deterministic mapping
#                     # ------------------------------------------------
#                     decision = self._decide_event(description)

#                 # ----------------------------------------------------
#                 # 🔥 4) Optional second disambiguation
#                 # ----------------------------------------------------
#                 try:
#                     ambiguous = False
#                     dl = description.lower()
#                     if decision.get("event") in ("type", "unknown") and "click" in dl:
#                         ambiguous = True
#                     if ambiguous:
#                         llm2 = ma.decide_event_llm(description=description, bbox=bbox, image_path=shot)
#                         if llm2 and llm2.get("event") not in ("unknown", None):
#                             decision = llm2

#                 except Exception as e:
#                     logger.debug(f"LLM disambiguation failed: {e}")

#                 # FINAL: perform using chosen event
#                 exec_result = {
#                     **self._perform(bbox, decision),
#                     "bbox": bbox,
#                     "decision": decision
#                 }


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

#             logger.debug("Step attempt %d failed validation: %s", attempt, validation)

#             # If we've reached max_attempts -> replan via MainAIAgent
#             if attempt >= max_attempts:
#                 failed_step_yaml = yaml.safe_dump({"step": step}, sort_keys=False)
#                 failure_details_yaml = yaml.safe_dump({"execution": last_execution, "validation": last_validation}, sort_keys=False)
#                 from os_automation.agents.main_ai import MainAIAgent
#                 ma = MainAIAgent()
#                 # ensure original_prompt is available and safe to use
#                 oprompt = original_prompt if ('original_prompt' in locals() and original_prompt) else description
#                 try:
#                     replan_yaml = ma.replan_on_failure(oprompt, failed_step_yaml, failure_details_yaml)
#                     replan_parsed = yaml.safe_load(replan_yaml)
#                 except Exception as e:
#                     replan_parsed = {"escalation": {"reason": "replan_failed_parse", "error": str(e), "raw": replan_yaml if 'replan_yaml' in locals() else None}}

#                 logger.warning("Step escalated to planner after %d attempts for: %s", attempt, description)
#                 return yaml.safe_dump({
#                     "execution": {"attempts": attempt, "last": last_execution},
#                     "validation": last_validation,
#                     "escalate": True,
#                     "replan": replan_parsed
#                 }, sort_keys=False)


#             time.sleep(0.6)

#         return yaml.safe_dump({
#             "execution": {"attempts": attempt, "last": last_execution},
#             "validation": last_validation,
#             "escalate": True,
#             "escalation_reason": "max_attempts_reached"
#         }, sort_keys=False)


#     # ====================================================================
#     # BACKWARDS + FORWARD COMPATIBLE run_step()
#     # ====================================================================
#     # def run_step(self, step=None, step_id=None, step_description=None, validator_agent=None, max_attempts: int = None, **kwargs):
        
#     def run_step(self, step=None, step_id=None, step_description=None,
#              validator_agent=None, max_attempts=None,
#              original_prompt=None, **kwargs):    
#         """
#         Supports both:
#             run_step(step=<dict>)
#         AND
#             run_step(step_id=1, step_description="Click search box")

#         This is required because Orchestrator now calls:
#             run_step(step_description=..., validator_agent=..., max_attempts=...)
#         """
        
#         # --------------------------
#         # Normalize to a step dict
#         # --------------------------
#         if step is None:
#             step = {
#                 "step_id": step_id,
#                 "description": step_description
#             }

#         if "description" not in step or step["description"] is None:
#             raise ValueError("run_step(): 'description' missing from step")

#         if "step_id" not in step or step["step_id"] is None:
#             step["step_id"] = step_id or 1

#          # ---- Execute via modern YAML pipeline ----
#         yaml_result = self.run_step_yaml(
#             yaml.safe_dump(step),
#             validator_agent=validator_agent or self.validator,
#             max_attempts=(max_attempts or self.max_attempts),
#             original_prompt=original_prompt or step_description
#         )

#         # ---- Convert YAML → Python dict ----
#         try:
#             return yaml.safe_load(yaml_result)
#         except Exception:
#             return {
#                 "execution": None,
#                 "validation": {"validation_status": "fail", "reason": "invalid_yaml"},
#                 "raw": yaml_result
#             }



# os_automation/agents/executor_agent.py
import os
import time
import uuid
import yaml
import logging
import random
from typing import Optional, Dict, Any, List, Callable

import platform
import subprocess
import re

from PIL import Image
import pyautogui

from os_automation.agents.validator_agent import ValidatorAgent
from os_automation.core.registry import registry

# try to import MainAIAgent only if available (used for optional rewrite)
try:
    from os_automation.agents.main_ai import MainAIAgent
except Exception:
    MainAIAgent = None

logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = True

# Default attempts: retry 3 times; after that, escalate to planner
DEFAULT_MAX_ATTEMPTS = 3


# -------------------------------------------------------
# Screenshot helper
# -------------------------------------------------------
def _screenshot(output_dir: str, prefix: str = "shot") -> str:
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

    - Receives atomic step descriptions from MainAIAgent.
    - Uses OSAtlas (or other detection adapter) to locate UI elements.
    - Uses PyAutoGUIAdapter to perform events (click, type, keypress, scroll).
    - Uses ValidatorAgent to validate BEFORE/AFTER screenshots.
    - Retries each step up to max_attempts; if still failing, escalates to planner.
    """

    def __init__(
        self,
        default_detection: str = "osatlas",
        default_executor: str = "pyautogui",
        openai_model: str = "gpt-4o",
        chrome_preference: bool = True,
        output_dir: str = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        self.execution_mode = "gui"  # or "terminal"

        self.validator = ValidatorAgent()

        self.default_detection = default_detection
        self.default_executor = default_executor
        self.openai_model = openai_model
        self.chrome_preference = chrome_preference

        self.max_attempts = int(max_attempts)

        self.output_dir = output_dir or os.path.join(
            os.getcwd(), "os_automation_output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        try:
            pyautogui.FAILSAFE = True
        except Exception:
            pass

        # Optional rewrite using MainAIAgent when OpenAI key available.
        # If not available, use a lightweight fallback rewrite function.
        self._rewrite_fn: Optional[Callable[[str], str]] = None
        try:
            if MainAIAgent and os.getenv("OPENAI_API_KEY"):
                ma = MainAIAgent()
                # use the agent's method for rewrite (may call LLM)
                self._rewrite_fn = ma.rewrite_ui_query
            else:
                # local fallback
                self._rewrite_fn = self._local_rewrite_ui_query
        except Exception:
            self._rewrite_fn = self._local_rewrite_ui_query

    # ====================================================================
    # ADAPTERS
    # ====================================================================
    def _get_detection_adapter(self):
        factory = registry.get_adapter(self.default_detection)
        if factory is None:
            return None
        return factory() if callable(factory) else factory

    def _get_executor_adapter(self):
        factory = registry.get_adapter(self.default_executor)
        if factory is None:
            return None
        return factory() if callable(factory) else factory

    # ====================================================================
    # LOCAL REWRITE (fallback)
    # ====================================================================
    def _local_rewrite_ui_query(self, description: str) -> str:
        """
        Lightweight heuristic to convert vague step descriptions into short
        queries that detectors handle better.
        """
        desc = (description or "").lower()
        # common mappings
        mapping = {
            "search box": "address bar",
            "search": "address bar",
            "address bar": "address bar",
            "search box": "search",
            "searchbar": "search",
            "search bar": "search",
            "google search": "search",
            "vscode explorer": "explorer",
            "explorer icon": "explorer",
            "new file": "new file",
            "new file button": "new file",
            "file name field": "file name",
            "filename field": "file name",
            "first result": "first result",
            "first link": "first result",
            "profile icon": "profile icon",
            "menu": "menu",
            "settings": "settings",
            "three dots": "menu",
            "submit": "submit",
            "ok": "ok button",
            "close": "close button",
            "play": "play button",
            "pause": "pause button",
        }
        for k, v in mapping.items():
            if k in desc:
                return v

        # extract quoted text
        m = re.search(r"['\"]([^'\"]{1,60})['\"]", description)
        if m:
            return m.group(1)

        # last-resort: pick last noun-like token
        tokens = re.findall(r"[a-zA-Z0-9_-]{2,50}", desc)
        if tokens:
            # prefer short tokens near start that indicate UI
            for t in tokens:
                if t in ("button", "icon", "link", "menu", "search", "address", "file", "run"):
                    return t
            return tokens[-1]

        return description.strip()
    
    
    # ====================================================================
    # a REAL click policy
    # ====================================================================
    def _safe_click_point(self, bbox: List[int]) -> List[int]:
        """
        Convert bbox to a safe click coordinate.
        This is the SINGLE source of truth for click safety.
        """
        x, y, w, h = bbox

        # Base center
        cx = x + w * 0.5
        cy = y + h * 0.5

        # ---- Dynamic heuristics (NO task-specific strings) ----

        # Wide + short → likely input / address bar
        aspect_ratio = w / max(h, 1)

        if aspect_ratio > 4.0:
            # Inputs behave better slightly below center
            cy = y + h * 0.60
        else:
            cy = y + h * 0.50

        # ---- Micro jitter (human-like) ----
        cx += random.randint(-3, 3)
        cy += random.randint(-2, 2)

        return [int(cx), int(cy)]


    # ====================================================================
    # DETECT BBOX
    # ====================================================================
    def _detect_bbox(
        self, description: str, image_path: Optional[str] = None
    ) -> Optional[List[int]]:
        """
        Use detection adapter (OSAtlas or other) to find target region.

        Returns bbox as [x, y, w, h] in SCREEN coordinates or None.
        Strategy:
          - rewrite query to something detector-friendly
          - call detector with image + text
          - prefer structured bbox from response
          - if only point provided, create an adaptive bbox sized by screen dims
          - if raw_output contains coords, parse them
        """
        det = self._get_detection_adapter()
        if not det:
            logger.warning("No detection adapter configured.")
            return None

        shot = image_path or _screenshot(self.output_dir, "shot")

        # Prepare a short query to improve detection
        query = description or ""
        try:
            if self._rewrite_fn:
                rq = self._rewrite_fn(description)
                if isinstance(rq, str) and rq.strip():
                    query = rq
        except Exception as e:
            logger.debug("rewrite_ui_query failed: %s", e)
            # fallback to local cleanup
            query = self._local_rewrite_ui_query(description)

        # Try detector call with both text keys (some adapters accept different names)
        try:
            res = det.detect({"image_path": shot, "text": query})
        except TypeError:
            try:
                res = det.detect({"image_path": shot, "description": query})
            except Exception as e:
                logger.debug("Detection error (2): %s", e)
                return None
        except Exception as e:
            logger.debug("Detection error (1): %s", e)
            return None

        # Normalize response into dict if adapter returned something else
        if not isinstance(res, dict):
            # maybe direct coordinate or list
            parsed = None
            try:
                # try parse "x,y" or "[x,y]" style
                nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", str(res))]
                if len(nums) >= 2:
                    parsed = (nums[0], nums[1])
            except Exception:
                parsed = None

            if parsed:
                # create small adaptive bbox from point
                cx, cy = int(parsed[0]), int(parsed[1])
                w = max(30, int(pyautogui.size().width * 0.03))
                h = max(20, int(pyautogui.size().height * 0.03))
                return [cx - w // 2, cy - h // 2, w, h]
            return None

        # If the adapter returned a structured dict, prefer bbox
        bbox = res.get("bbox")
        dtype = res.get("type")
        conf = float(res.get("confidence", 0.0) or 0.0)

        # If bbox exists and looks sane (x,y,w,h)
        if bbox and len(bbox) >= 4:
            try:
                x, y, w, h = bbox[:4]
                # If values are x1,y1,x2,y2 convert to x,y,w,h
                # Heuristic: if w > 2000 or h > 2000 then probably x2/y2 form
                if (w > 2000) or (h > 2000) or (int(x) < 0) or (int(y) < 0):
                    # assume [x1,y1,x2,y2] format
                    x1, y1, x2, y2 = bbox[:4]
                    x, y, w, h = int(x1), int(y1), int(max(1, x2 - x1)), int(max(1, y2 - y1))
                else:
                    x, y, w, h = int(x), int(y), int(max(1, w)), int(max(1, h))
                return [x, y, w, h]
            except Exception:
                logger.debug("Failed to normalize returned bbox: %s", bbox)

        # If no bbox but there is a point: create adaptive bbox
        point = res.get("point")
        if point and isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                cx, cy = int(point[0]), int(point[1])
                screen_w, screen_h = pyautogui.size()
                # box size ~ 3% of screen width/height, clamped
                bw = max(28, int(screen_w * 0.03))
                bh = max(20, int(screen_h * 0.03))
                return [cx - bw // 2, cy - bh // 2, bw, bh]
            except Exception:
                logger.debug("Failed to use point -> bbox from detector: %s", point)

        # If adapter returned raw text that may include coords, try to parse
        raw = ""
        for key in ("raw_output", "raw", "response", "bbox", "text"):
            if isinstance(res.get(key), str) and res.get(key).strip():
                raw = res.get(key)
                break
        if not raw:
            raw = str(res.get("raw") or res.get("response") or "")

        # Try extract four numbers from raw formatted like [x1,y1,x2,y2] or "x1,y1,x2,y2"
        try:
            nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", raw)]
            if len(nums) >= 4:
                x1, y1, x2, y2 = nums[:4]
                x, y, w, h = int(x1), int(y1), int(max(1, x2 - x1)), int(max(1, y2 - y1))
                return [x, y, w, h]
        except Exception:
            pass

        # Last resort: attempt to parse a single point in raw text
        try:
            nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", raw)]
            if len(nums) >= 2:
                cx, cy = int(nums[0]), int(nums[1])
                screen_w, screen_h = pyautogui.size()
                bw = max(28, int(screen_w * 0.03))
                bh = max(20, int(screen_h * 0.03))
                return [cx - bw // 2, cy - bh // 2, bw, bh]
        except Exception:
            pass


        # Safety check only if bbox exists
        if bbox:
            try:
                x, y, w, h = bbox
                screen_w, screen_h = pyautogui.size()
                if x < 0 or y < 0 or x + w > screen_w or y + h > screen_h:
                    logger.warning("Discarding out-of-screen bbox")
                    return None
            except Exception:
                return None

    
        # Finally: no usable detection
        return None

    # ====================================================================
    # EVENT MAPPING  (description → event fields)
    # ====================================================================
    def _map_description_to_event(self, description: str) -> Dict[str, Any]:
        """
        Interpret a natural-language step description and convert it into a
        low-level event structure for PyAutoGUIAdapter.
        """
        
        import re

        desc = (description or "").strip()
        low = desc.lower()

        # TYPE 'text'
        m = re.search(r"type\s+['\"]([^'\"]+)['\"]", desc, re.IGNORECASE)
        if m:
            return {"event": "type", "text": m.group(1)}

        m2 = re.search(r"['\"]([^'\"]+)['\"]", desc)
        if "type" in low and m2:
            return {"event": "type", "text": m2.group(1)}

        if "press enter" in low or low == "enter":
            return {"event": "keypress", "key": "enter"}

        if "backspace" in low:
            return {"event": "keypress", "key": "backspace"}

        if "delete" in low and "backspace" not in low:
            return {"event": "keypress", "key": "delete"}
        
        # Generic Ctrl+<Key> hotkeys
        m = re.search(r"press\s+ctrl\+([a-z])", low)
        if m:
            return {"event": "hotkey", "keys": ["ctrl", m.group(1)]}

        if "select all" in low or "ctrl+a" in low:
            return {"event": "hotkey", "keys": ["ctrl", "a"]}

        if "paste" in low or "ctrl+v" in low:
            return {"event": "hotkey", "keys": ["ctrl", "v"]}

        if "arrow left" in low:
            return {"event": "keypress", "key": "left"}
        if "arrow right" in low:
            return {"event": "keypress", "key": "right"}
        if "arrow up" in low:
            return {"event": "keypress", "key": "up"}
        if "arrow down" in low:
            return {"event": "keypress", "key": "down"}

        if "scroll down" in low:
            return {"event": "scroll", "direction": "down"}
        if "scroll up" in low:
            return {"event": "scroll", "direction": "up"}

        if "double click" in low:
            return {"event": "double_click"}
        if "right click" in low or "context menu" in low:
            return {"event": "right_click"}
        
        # Calculator / operator buttons
        m = re.search(r"press\s+'([^']+)'", low)
        if m:
            symbol = m.group(1)
            return {"event": "keypress", "key": symbol}


        if "click" in low or "open " in low or "select " in low:
            return {"event": "click"}

        if "wait" in low or "pause" in low or low in ("noop", "no-op"):
            return {"event": "noop"}
        
        if "press super key" in low:
            return {"event": "hotkey", "keys": ["win"]}

        if "press windows key" in low:
            return {"event": "hotkey", "keys": ["win"]}

        if "press command+space" in low:
            return {"event": "hotkey", "keys": ["command", "space"]}

        # Fallback: treat as typing (e.g., ambiguous "Type something...")
        return {
            "event": "unknown",
            "error": "ambiguous_step_no_action"
        }


    # ====================================================================
    # PERFORM VIA EXECUTOR ADAPTER (PyAutoGUI)
    # ====================================================================
    def _perform_via_adapter(
        self,
        bbox: Optional[List[int]],
        event_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Use PyAutoGUIAdapter (or configured executor adapter) to perform
        the low-level event. Always screenshot BEFORE & AFTER.
        """
        exec_adapter = self._get_executor_adapter()

        before = _screenshot(self.output_dir, "before")
        
        # -------------------------------
        # 🛡️ Adapter capability validation
        # -------------------------------
        event = event_spec.get("event")

        # Adapter must declare supported events
        supported = getattr(exec_adapter, "SUPPORTED_EVENTS", None)

        if supported is not None and event not in supported:
            logger.error(
                "Adapter %s does not support event '%s'. Supported=%s",
                exec_adapter.__class__.__name__,
                event,
                supported,
            )
            after = _screenshot(self.output_dir, "after_unsupported_event")
            return {
                "status": "failed",
                "before": before,
                "after": after,
                "error": f"unsupported_event:{event}",
                "event": event,
            }


        if not exec_adapter:
            logger.error("No executor adapter configured.")
            after = _screenshot(self.output_dir, "after")
            return {
                "status": "failed",
                "before": before,
                "after": after,
                "error": "no_executor_adapter",
            }

        event = event_spec.get("event")
        text = event_spec.get("text")
        key = event_spec.get("key")
        keys = event_spec.get("keys")
        direction = event_spec.get("direction")

        step_for_adapter: Dict[str, Any] = {
            "event": event,
            "bbox": bbox or [10, 10, 20, 20],  # tiny default if None
        }

        if text is not None:
            step_for_adapter["text"] = text
        if key is not None:
            step_for_adapter["key"] = key
        if keys is not None:
            step_for_adapter["keys"] = keys
        if direction is not None:
            step_for_adapter["direction"] = direction
            

        try:
            adapter_result = exec_adapter.execute(step_for_adapter)
        except TypeError:
            adapter_result = exec_adapter.execute(step_for_adapter)
        except Exception as e:
            logger.exception("Executor adapter error: %s", e)
            after = _screenshot(self.output_dir, "after")
            return {
                "status": "failed",
                "before": before,
                "after": after,
                "error": str(e),
                "adapter_step": step_for_adapter,
            }

        after = _screenshot(self.output_dir, "after")

        if not isinstance(adapter_result, dict):
            adapter_result = {"status": "success" if adapter_result else "failed"}

        return {
            "status": adapter_result.get("status", "failed"),
            "before": before,
            "after": after,
            "bbox": bbox,
            "event": event,
            "adapter_raw": adapter_result,
        }

    # ====================================================================
    # SPECIAL SYSTEM ACTIONS
    # ====================================================================
    def _handle_open_terminal(self, step: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_mode = "terminal"

        desc = (step.get("description") or "").strip()
        logger.info("Handling special step: %s", desc)

        before = _screenshot(self.output_dir, "before")
        home = os.path.expanduser("~")
        system = platform.system()

        try:
            if system == "Linux":
                proc = None

                for cmd in (
                    ["gnome-terminal"],
                    ["konsole"],
                    ["x-terminal-emulator"],
                    ["xfce4-terminal"],
                ):
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            cwd=home,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        break
                    except Exception:
                        continue
                else:
                    proc = subprocess.Popen(
                        ["xterm"],
                        cwd=home,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )

                # ⏳ allow terminal window to appear
                time.sleep(1.2)

                # 🔑 HARD GUI FOCUS (this is what your reference repo relies on)
                import pyautogui
                screen_w, screen_h = pyautogui.size()
                pyautogui.click(screen_w // 2, screen_h // 2)
                time.sleep(0.2)

            elif system == "Darwin":
                subprocess.Popen(["open", "-a", "Terminal"], cwd=home)
                time.sleep(1.2)

            elif system.startswith("Win"):
                subprocess.Popen(["cmd.exe"], cwd=home)
                time.sleep(1.2)

            after = _screenshot(self.output_dir, "after")

            exec_res = {"status": "success", "before": before, "after": after}

        except Exception as e:
            after = _screenshot(self.output_dir, "after")
            exec_res = {
                "status": "failed",
                "before": before,
                "after": after,
                "error": str(e),
            }

        exec_yaml = yaml.safe_dump({"step": step, "execution": exec_res}, sort_keys=False)
        validation_yaml = self.validator.validate_step_yaml(exec_yaml)
        validation = yaml.safe_load(validation_yaml)

        return {
            "execution": {"attempts": 1, "last": exec_res},
            "validation": validation,
            "escalate": validation.get("validation_status") != "pass",
        }


    def _handle_open_browser(self, step: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_mode = "gui"

        desc = (step.get("description") or "").strip()
        logger.info("Handling special step: %s", desc)

        before = _screenshot(self.output_dir, "before")
        system = platform.system()

        try:
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
                    except Exception:
                        continue
                if not launched:
                    subprocess.Popen(["xdg-open", "https://google.com"])

            elif system == "Darwin":
                subprocess.Popen(
                    [
                        "open",
                        "-n",
                        "-a",
                        "Google Chrome",
                        "--args",
                        "--new-window",
                        "https://google.com",
                    ]
                )

            elif system.startswith("Win"):
                try:
                    subprocess.Popen(
                        [
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            "--new-window",
                            "https://google.com",
                        ]
                    )
                except Exception:
                    os.startfile("chrome")

            else:
                import webbrowser

                webbrowser.open("https://google.com", new=1)

            time.sleep(2.5)
            after = _screenshot(self.output_dir, "after")

            exec_res = {"status": "success", "before": before, "after": after}
        except Exception as e:
            after = _screenshot(self.output_dir, "after")
            exec_res = {
                "status": "failed",
                "before": before,
                "after": after,
                "error": str(e),
            }

        exec_yaml = yaml.safe_dump({"step": step, "execution": exec_res}, sort_keys=False)
        validation_yaml = self.validator.validate_step_yaml(exec_yaml)
        validation = yaml.safe_load(validation_yaml)

        return {
            "execution": {"attempts": 1, "last": exec_res},
            "validation": validation,
            "escalate": validation.get("validation_status") != "pass",
        }


    def _handle_open_file_explorer(self, step):
        system = platform.system()
        before = _screenshot(self.output_dir, "before")

        try:
            if system == "Linux":
                subprocess.Popen(["xdg-open", os.path.expanduser("~")])
            elif system == "Darwin":
                subprocess.Popen(["open", os.path.expanduser("~")])
            elif system.startswith("Win"):
                subprocess.Popen(["explorer.exe"])

            time.sleep(1.5)
            after = _screenshot(self.output_dir, "after")

            return {
                "execution": {"attempts": 1, "last": {"status": "success", "before": before, "after": after}},
                "validation": {"validation_status": "pass"},
                "escalate": False
            }

        except Exception as e:
            after = _screenshot(self.output_dir, "after")
            return {
                "execution": {"attempts": 1, "last": {"status": "failed", "error": str(e)}},
                "validation": {"validation_status": "fail"},
                "escalate": True
            }

    # ====================================================================
    # MAIN YAML EXECUTION FOR ONE STEP
    # ====================================================================
    def run_step_yaml(
        self,
        step_yaml: str,
        validator_agent: Optional[ValidatorAgent],
        max_attempts: Optional[int] = None,
        original_prompt: Optional[str] = None,
    ) -> str:
        validator_agent = validator_agent or self.validator
        max_attempts = max_attempts or self.max_attempts

        step = yaml.safe_load(step_yaml) or {}
        description = step.get("description") or ""
        step_id = step.get("step_id", 0)
        low = description.lower().strip()
        
        
        is_gui_type = low.startswith("type ")
        is_gui_enter = low == "press enter" or low == "enter"
        
        # ============================================================
        # OS LAUNCHER HOTKEY SHORT-CIRCUIT
        # ============================================================
        if "press super key" in low or "press windows key" in low:
            before = _screenshot(self.output_dir, "before_launcher")
            pyautogui.press("win")
            time.sleep(0.6)
            after = _screenshot(self.output_dir, "after_launcher")

            return yaml.safe_dump(
                {
                    "execution": {
                        "attempts": 1,
                        "last": {
                            "status": "success",
                            "before": before,
                            "after": after,
                            "event": "os_launcher",
                        },
                    },
                    "validation": {"validation_status": "pass"},
                    "escalate": False,
                },
                sort_keys=False,
            )

        if "press command+space" in low:
            before = _screenshot(self.output_dir, "before_launcher")
            pyautogui.hotkey("command", "space")
            time.sleep(0.6)
            after = _screenshot(self.output_dir, "after_launcher")

            return yaml.safe_dump(
                {
                    "execution": {
                        "attempts": 1,
                        "last": {
                            "status": "success",
                            "before": before,
                            "after": after,
                            "event": "spotlight",
                        },
                    },
                    "validation": {"validation_status": "pass"},
                    "escalate": False,
                },
                sort_keys=False,
            )
        
        # ============================================================
        # GUI TYPE / ENTER SHORT-CIRCUIT (NO BBOX, NO RETRY)
        # ============================================================
        if is_gui_type:
            before = _screenshot(self.output_dir, "before_gui_type")
            try:
                m = re.search(r"['\"]([^'\"]+)['\"]", description)
                if m:
                    # pyautogui.write(m.group(1), interval=0.03)
                    text = m.group(1)
                    pyautogui.write(text, interval=0.03)

                    # ⏳ HARD SAFETY DELAY (length-aware)
                    time.sleep(max(0.3, len(text) * 0.02))
                    
                after = _screenshot(self.output_dir, "after_gui_type")

                return yaml.safe_dump({
                    "execution": {
                            "attempts": 1,
                        "last": {
                            "status": "success",
                            "before": before,
                            "after": after,
                            "event": "gui_type"
                        }
                    },
                    "validation": {"validation_status": "pass"},
                    "escalate": False
                }, sort_keys=False)

            except Exception as e:
                after = _screenshot(self.output_dir, "after_gui_type")
                return yaml.safe_dump({
                    "execution": {
                        "attempts": 1,
                        "last": {
                            "status": "failed",
                            "before": before,
                            "after": after,
                            "error": str(e)
                        }
                    },
                    "validation": {"validation_status": "fail"},
                    "escalate": True
                }, sort_keys=False)


        if is_gui_enter:
            before = _screenshot(self.output_dir, "before_gui_enter")
            pyautogui.press("enter")
            after = _screenshot(self.output_dir, "after_gui_enter")

            return yaml.safe_dump({
                "execution": {
                    "attempts": 1,
                    "last": {
                        "status": "success",
                        "before": before,
                        "after": after,
                        "event": "gui_enter"
                    }
                },
                "validation": {"validation_status": "pass"},
                "escalate": False
            }, sort_keys=False)
            
            
        # ============================================================
        # WAIT / PAUSE SHORT-CIRCUIT (NO BBOX, NO RETRY)
        # ============================================================
        if "wait" in low or "pause" in low:
            logger.info("Wait step detected → sleeping")

            before = _screenshot(self.output_dir, "before_wait")

            # Default wait duration
            duration = 1.5

            # Optional: parse "wait 3 seconds"
            m = re.search(r"wait\s+(\d+(?:\.\d+)?)", low)
            if m:
                duration = float(m.group(1))

            time.sleep(duration)
            
            # # 🔑 CONTEXT SWITCH: after app launch waits, assume GUI focus
            # if "wait for application to open" in low:
            #     self.execution_mode = "gui"

            after = _screenshot(self.output_dir, "after_wait")

            return yaml.safe_dump(
                {
                    "execution": {
                        "attempts": 1,
                        "last": {
                            "status": "success",
                            "before": before,
                            "after": after,
                            "event": "wait",
                            "duration": duration,
                        },
                    },
                    "validation": {"validation_status": "pass"},
                    "escalate": False,
                },
                sort_keys=False,
            )

        
        # ============================================================
        # TERMINAL MODE SHORT-CIRCUIT (CRITICAL FIX)
        # ============================================================
        is_terminal_type = (
            self.execution_mode == "terminal" and low.startswith("type ")
        )

        is_terminal_enter = (
            self.execution_mode == "terminal"
            and ("press enter" in low or low == "enter")
        )


        if is_terminal_type or is_terminal_enter:
            logger.info("Terminal input detected → bypassing bbox detection")

            before = _screenshot(self.output_dir, "before_terminal")

            try:
                # DO NOT click anywhere
                # DO NOT detect bbox
                if is_terminal_type:
                    m = re.search(r"['\"]([^'\"]+)['\"]", description)
                    if m:
                        # pyautogui.write(m.group(1), interval=0.03)
                        text = m.group(1)
                        pyautogui.write(text, interval=0.03)

                        # ⏳ terminal buffers need a bit more time
                        time.sleep(max(0.4, len(text) * 0.025))


                if is_terminal_enter:
                    pyautogui.press("enter")

                after = _screenshot(self.output_dir, "after_terminal")

                exec_res = {
                    "status": "success",
                    "before": before,
                    "after": after,
                    "event": "terminal_input",
                }

            except Exception as e:
                after = _screenshot(self.output_dir, "after_terminal")
                exec_res = {
                    "status": "failed",
                    "before": before,
                    "after": after,
                    "error": str(e),
                }

            exec_yaml = yaml.safe_dump({"step": step, "execution": exec_res}, sort_keys=False)
            validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
            validation = yaml.safe_load(validation_yaml)

            return yaml.safe_dump(
                {
                    "execution": {"attempts": 1, "last": exec_res},
                    "validation": validation,
                    "escalate": validation.get("validation_status") != "pass",
                },
                sort_keys=False,
            )

        # Special-case handlers
        if low.startswith("open terminal"):
            result = self._handle_open_terminal(step)
            return yaml.safe_dump(result, sort_keys=False)

        if low in ("open browser", "open the browser") or "open chrome" in low:
            result = self._handle_open_browser(step)
            return yaml.safe_dump(result, sort_keys=False)
        
        if low.startswith("open file explorer"):
            return yaml.safe_dump(self._handle_open_file_explorer(step), sort_keys=False)


        attempt = 0
        last_execution = None
        last_validation = None

        while attempt < max_attempts:
            attempt += 1
            logger.info("Executor attempt %d for step %s: %s", attempt, step_id, description)

            # Screenshot BEFORE for visual state check
            shot = _screenshot(self.output_dir, "shot")
            bbox = self._detect_bbox(description, image_path=shot)

            # No bbox found
            if bbox is None:
                logger.warning("No bbox found → waiting and retrying detection")

                time.sleep(0.7)

                shot_retry = _screenshot(self.output_dir, "shot_retry")
                bbox = self._detect_bbox(description, image_path=shot_retry)

                if bbox is None:
                    exec_result = {
                        "status": "failed",
                        "before": _screenshot(self.output_dir, "before_no_bbox"),
                        "after": _screenshot(self.output_dir, "after_no_bbox"),
                        "error": "no_bbox_detected"
                    }

                    last_execution = exec_result
                    exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
                    validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
                    last_validation = yaml.safe_load(validation_yaml)

                    time.sleep(0.8)
                    continue 
            
            event_spec = self._map_description_to_event(description)


            # ---------------- SAFE CLICK POLICY ----------------
            if event_spec.get("event") == "click":
                cx, cy = self._safe_click_point(bbox)
                # event_spec = {
                #     "event": "click_at",
                #     "coords": [cx, cy],
                # }
                event_spec = {
                    "event": "click",
                    "bbox": [cx - 2, cy - 2, 4, 4],  # tiny bbox centered at safe point
                }


            exec_result = self._perform_via_adapter(bbox, event_spec)
            last_execution = exec_result

            exec_yaml = yaml.safe_dump({"step": step, "execution": exec_result}, sort_keys=False)
            validation_yaml = validator_agent.validate_step_yaml(exec_yaml)
            validation = yaml.safe_load(validation_yaml)
            last_validation = validation

            if validation.get("validation_status") == "pass":
                return yaml.safe_dump(
                    {"execution": {"attempts": attempt, "last": last_execution},
                     "validation": validation, "escalate": False},
                    sort_keys=False,
                )

            logger.debug("Step attempt %d failed: %s", attempt, validation)
            time.sleep(1.1)

        # All attempts failed → escalate to planner
        return yaml.safe_dump(
            {"execution": {"attempts": attempt, "last": last_execution},
             "validation": last_validation,
             "escalate": True},
            sort_keys=False,
        )

    # ====================================================================
    # BACKWARDS + ORCHESTRATOR-COMPATIBLE ENTRYPOINT
    # ====================================================================
    def run_step(
        self,
        step: Optional[Dict[str, Any]] = None,
        step_id: Optional[int] = None,
        step_description: Optional[str] = None,
        validator_agent: Optional[ValidatorAgent] = None,
        max_attempts: Optional[int] = None,
        original_prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if step is None:
            step = {
                "step_id": step_id or 1,
                "description": step_description,
            }

        if "description" not in step or step["description"] is None:
            raise ValueError("run_step(): 'description' missing from step")

        if "step_id" not in step or step["step_id"] is None:
            step["step_id"] = step_id or 1

        yaml_result = self.run_step_yaml(
            yaml.safe_dump(step),
            validator_agent=validator_agent or self.validator,
            max_attempts=max_attempts or self.max_attempts,
            original_prompt=original_prompt or step_description,
        )

        try:
            return yaml.safe_load(yaml_result)
        except Exception:
            return {
                "execution": None,
                "validation": {
                    "validation_status": "fail",
                    "reason": "invalid_yaml",
                },
                "raw": yaml_result,
            }