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


# ---------------------------------------------------------------------
# VALIDATOR AGENT (FINAL VERSION)
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# VALIDATOR AGENT (FINAL VERSION WITH WRONG-FIELD DETECTION)
# ---------------------------------------------------------------------
class ValidatorAgent:
    TYPE_THRESHOLD = 0.3
    CLICK_THRESHOLD = 0.6
    NAVIGATION_THRESHOLD = 5.0

    def validate_step_yaml(self, exec_yaml: str) -> str:
        import yaml
        try:
            data = yaml.safe_load(exec_yaml) or {}
        except Exception:
            return yaml.safe_dump({"validation_status": "fail", "details": {"reason": "invalid_exec_yaml"}})

        # The existing logic uses:
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

        # ---------------------------------------------------------
        # TYPE validation (OCR first)
        # ---------------------------------------------------------
        if "type" in desc:
            import re
            m = re.search(r"['\"]([^'\"]+)['\"]", desc)
            expected = m.group(1) if m else ""

            if OCR_AVAILABLE and expected:
                ocr_after = _ocr(after).lower()

                # 1) typed text found → good
                if expected.lower() in ocr_after:

                    # ---------------------------------------------------------
                    # WRONG FIELD DETECTION (THE IMPORTANT FIX)
                    # ---------------------------------------------------------
                    # if expected typed text is present BUT search URL missing,
                    # that means text is inside URL bar instead of search field.
                    if "google.com/search" not in ocr_after:
                        return yaml.safe_dump({
                            "validation_status": "fail",
                            "details": {
                                "reason": "typed_in_wrong_input_field (omnibox instead of search box)",
                                "ocr_excerpt": ocr_after[:200]
                            }
                        })

                    # else → typed correctly into search box
                    return yaml.safe_dump({
                        "validation_status": "pass",
                        "details": {"method": "ocr", "matched": expected}
                    })

                # OCR did not find text
                return yaml.safe_dump({
                    "validation_status": "fail",
                    "details": {"method": "ocr",
                                "expected": expected,
                                "ocr_excerpt": ocr_after[:200]}
                })

            # fallback pixel diff
            return yaml.safe_dump({
                "validation_status": "pass" if diff > self.TYPE_THRESHOLD else "fail",
                "details": {"method": "pixel", "diff": diff}
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

