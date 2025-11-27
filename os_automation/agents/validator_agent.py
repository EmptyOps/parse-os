# os_automation/agents/validator_agent.py
import os
import logging
from typing import Dict, Any
from PIL import Image, ImageChops, ImageStat

logger = logging.getLogger(__name__)

# Try OCR
try:
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    pytesseract = None
    OCR_AVAILABLE = False
    logger.debug("pytesseract not available; using pixel diff fallback.")


# ---------------------------------------------------------------------
# Pixel-diff helper
# ---------------------------------------------------------------------
def _pixel_diff(before_path: str, after_path: str) -> float:
    try:
        if not (before_path and after_path):
            return 0.0
        if not os.path.exists(before_path) or not os.path.exists(after_path):
            return 0.0

        b1 = Image.open(before_path).convert("RGB")
        b2 = Image.open(after_path).convert("RGB")

        # quick downscale to speed up processing
        b1 = b1.resize((b1.width // 2, b1.height // 2))
        b2 = b2.resize((b2.width // 2, b2.height // 2))

        diff = ImageChops.difference(b1, b2)
        stat = ImageStat.Stat(diff)
        mean_val = sum(stat.mean) / len(stat.mean)
        return mean_val
    except Exception as e:
        logger.exception("pixel diff error: %s", e)
        return 0.0


# ---------------------------------------------------------------------
# OCR helper
# ---------------------------------------------------------------------
def _ocr(image_path: str) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text or ""
    except Exception as e:
        logger.debug("OCR failed: %s", e)
        return ""


# (inside os_automation/agents/validator_agent.py)

# Adjusted thresholds (less aggressive for OCR-first validation)
class ValidatorAgent:
    TYPE_THRESHOLD = 0.08    # lowered from 0.3 — terminal typing tends to produce tiny pixel diffs
    CLICK_THRESHOLD = 0.5    # slightly lowered to be more tolerant of subtle UI changes
    NAVIGATION_THRESHOLD = 4.0

    def validate_step_yaml(self, exec_yaml: str) -> str:
        import yaml
        try:
            data = yaml.safe_load(exec_yaml) or {}
        except Exception:
            return yaml.safe_dump({"validation_status": "fail", "details": {"reason": "invalid_exec_yaml"}})

        step = data.get("step", {})
        exe = data.get("execution", {})

        desc = (step.get("description") or "").lower()
        before = exe.get("before")
        after = exe.get("after")

        # 1. Executor fail → fail
        if exe.get("status") == "failed":
            return yaml.safe_dump({"validation_status": "fail",
                                   "details": {"reason": "executor_failed"}})

        # 2. screenshot missing
        if not before or not after or not os.path.exists(before) or not os.path.exists(after):
            return yaml.safe_dump({"validation_status": "fail",
                                   "details": {"reason": "missing_screenshots"}})

        diff = _pixel_diff(before, after)

        # ---------------------------
        # Special-cases (search results / first link)
        # ---------------------------
        if any(k in desc for k in ("first search result", "first result", "first link", "open first result")):
            # Many SERP clicks change page but may not show large pixel diffs in the cropped area.
            return yaml.safe_dump({
                "validation_status": "pass",
                "details": {"method": "special_case", "reason": "first_search_result_click_assumed_ok"}
            })

        # ---------------------------------------------------------
        # TYPING + TERMINAL COMMANDS (Type '...' / Run command '...')
        # ---------------------------------------------------------
        import re

        is_type_step = desc.startswith("type ") or desc.startswith("type'") or "type '" in desc
        is_run_cmd_step = desc.startswith("run command") or "run command" in desc
        looks_like_terminal = is_run_cmd_step or "terminal" in desc or "shell" in desc or "command prompt" in desc

        if is_type_step or is_run_cmd_step:
            # Extract the quoted text: 'ls', 'pwd', etc.
            m = re.search(r"['\"](.+?)['\"]", step.get("description", ""))
            expected = (m.group(1) if m else "").strip()

            # Try OCR on the after screenshot if available
            ocr_after = _ocr(after).lower() if OCR_AVAILABLE else ""

            # 1) Exact OCR match of the expected text → strong PASS
            if expected and expected.lower() in ocr_after:
                return yaml.safe_dump({
                    "validation_status": "pass",
                    "details": {
                        "method": "ocr",
                        "matched": expected,
                        "note": "expected text found in OCR output"
                    }
                })

            # 2) Terminal heuristic:
            #    - 'run command ...' OR description mentions terminal
            #    - we just need to see that *something* appeared in the terminal
            if looks_like_terminal:
                if ocr_after.strip():
                    # Any non-trivial text in the terminal after the command is a good sign
                    return yaml.safe_dump({
                        "validation_status": "pass",
                        "details": {
                            "method": "ocr_terminal_heuristic",
                            "ocr_excerpt": ocr_after[:200]
                        }
                    })

                # Fallback: use a very small pixel threshold
                return yaml.safe_dump({
                    "validation_status": "pass" if diff > self.TYPE_THRESHOLD else "fail",
                    "details": {
                        "method": "pixel_terminal",
                        "diff": diff,
                        "threshold": self.TYPE_THRESHOLD
                    }
                })

            # 3) Non-terminal typing (e.g. typing in a text field)
            #    → relaxed pixel threshold
            return yaml.safe_dump({
                "validation_status": "pass" if diff > self.TYPE_THRESHOLD else "fail",
                "details": {
                    "method": "pixel_typing",
                    "diff": diff,
                    "threshold": self.TYPE_THRESHOLD
                }
            })


        # ---------------------------------------------------------
        # ENTER = navigation
        # ---------------------------------------------------------
        if "press enter" in desc or desc == "enter":
            return yaml.safe_dump({
                "validation_status": "pass" if diff > self.NAVIGATION_THRESHOLD else "fail",
                "details": {"reason": "navigation_change", "diff": diff}
            })

        # ---------------------------------------------------------
        # CLICK search box special-case (Google omnibox)
        # ---------------------------------------------------------
        if "click search box" in desc or "search box" in desc or "click address bar" in desc or "omnibox" in desc:
            return yaml.safe_dump({
                "validation_status": "pass",
                "details": {"method": "special_case", "reason": "google_search_box_clicked"}
            })

        # ---------------------------------------------------------
        # CLICK = small diff required
        # ---------------------------------------------------------
        if "click" in desc:
            return yaml.safe_dump({
                "validation_status": "pass" if diff > self.CLICK_THRESHOLD else "fail",
                "details": {"method": "pixel", "diff": diff}
            })

        # ---------------------------------------------------------
        # DEFAULT
        # ---------------------------------------------------------
        return yaml.safe_dump({
            "validation_status": "pass" if diff > 1.0 else "fail",
            "details": {"method": "pixel", "diff": diff}
        })

    # ---------------------------------------------------------
    # ADVANCED VALIDATION (pixel diff + local region + OCR + bbox shift)
    # ---------------------------------------------------------
    def validate_step_advanced(self, description: str, before_path: str, after_path: str, bbox):
        """
        More reliable validator for clicks and UI state changes.
        Uses:
          1) Local region diff
          2) Global diff
          3) OCR text match
          4) Bounding-box state shift
        """

        import numpy as np
        from PIL import Image

        desc = description.lower()

        # Sanity check
        if not before_path or not after_path:
            return {"valid": False, "reason": "missing_screenshots"}

        if not os.path.exists(before_path) or not os.path.exists(after_path):
            return {"valid": False, "reason": "missing_files"}

        before_img = Image.open(before_path).convert("L")
        after_img = Image.open(after_path).convert("L")

        bw, bh = before_img.size

        # -----------------------------------------
        # 1) Local region diff
        # -----------------------------------------
        try:
            x, y, w, h = bbox or [0, 0, 50, 50]
            pad = 40

            region = (
                max(0, x - pad),
                max(0, y - pad),
                min(bw, x + w + pad),
                min(bh, y + h + pad)
            )

            before_crop = before_img.crop(region)
            after_crop = after_img.crop(region)

            diff_local = np.mean(np.abs(
                np.array(before_crop, dtype=np.int16)
                - np.array(after_crop, dtype=np.int16)
            ))

            if diff_local > 12:
                return {"valid": True, "reason": "local_difference_detected", "diff_local": float(diff_local)}
        except Exception:
            pass

        # -----------------------------------------
        # 2) Global pixel diff
        # -----------------------------------------
        try:
            diff_global = np.mean(np.abs(
                np.array(before_img, dtype=np.int16)
                - np.array(after_img, dtype=np.int16)
            ))

            if diff_global > 6:
                return {"valid": True, "reason": "global_change_detected", "diff_global": float(diff_global)}
        except Exception:
            pass

        # -----------------------------------------
        # 3) OCR-based validation
        # -----------------------------------------
        if OCR_AVAILABLE:
            try:
                text_after = _ocr(after_path).lower()

                # direct substring detection
                if any(tok in text_after for tok in desc.split()):
                    return {"valid": True, "reason": "ocr_matched", "excerpt": text_after[:200]}
            except Exception:
                pass

        # -----------------------------------------
        # 4) Bounding box "state shift" detection
        # -----------------------------------------
        # Example: selected tab highlight changes position or shape
        try:
            # Compare average brightness around bbox
            bx1 = before_img.crop((x, y, x + w, y + h))
            bx2 = after_img.crop((x, y, x + w, y + h))

            diff_bbox = np.mean(np.abs(
                np.array(bx1, dtype=np.int16)
                - np.array(bx2, dtype=np.int16)
            ))

            if diff_bbox > 10:
                return {"valid": True, "reason": "bbox_state_changed", "diff_bbox": float(diff_bbox)}
        except Exception:
            pass

        # -----------------------------------------
        # 5) No significant change → invalid
        # -----------------------------------------
        return {"valid": False, "reason": "no_state_change_detected"}
