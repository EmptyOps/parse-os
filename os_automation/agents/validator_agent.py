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

# # os_automation/agents/validator_agent.py
# import os
# import logging
# from typing import Dict, Any
# from PIL import Image, ImageChops, ImageStat

# logger = logging.getLogger(__name__)

# # Try OCR
# try:
#     import pytesseract
#     OCR_AVAILABLE = True
# except Exception:
#     pytesseract = None
#     OCR_AVAILABLE = False
#     logger.debug("pytesseract not available; using pixel diff fallback.")


# # ---------------------------------------------------------------------
# # Pixel-diff helper (region + global)
# # ---------------------------------------------------------------------
# def _pixel_diff_values(before_path: str, after_path: str, box: tuple = None) -> float:
#     """
#     Compute mean pixel difference either for a small box or full image.
#     Returns a float (mean difference).
#     """
#     try:
#         if not (before_path and after_path):
#             return 0.0
#         if not os.path.exists(before_path) or not os.path.exists(after_path):
#             return 0.0

#         b1 = Image.open(before_path).convert("L")
#         b2 = Image.open(after_path).convert("L")

#         # If box provided, crop safely
#         if box:
#             W, H = b1.size
#             left = max(0, box[0])
#             top = max(0, box[1])
#             right = min(W, box[2])
#             bottom = min(H, box[3])
#             if right <= left or bottom <= top:
#                 # invalid box -> fallback to global
#                 box = None
#             else:
#                 b1 = b1.crop((left, top, right, bottom))
#                 b2 = b2.crop((left, top, right, bottom))

#         # quick downscale to speed up processing (for global diffs)
#         if b1.width > 800:
#             b1 = b1.resize((b1.width // 2, b1.height // 2))
#             b2 = b2.resize((b2.width // 2, b2.height // 2))

#         diff = ImageChops.difference(b1, b2)
#         stat = ImageStat.Stat(diff)
#         mean_val = sum(stat.mean) / len(stat.mean)
#         return mean_val
#     except Exception as e:
#         logger.exception("pixel diff error: %s", e)
#         return 0.0


# # ---------------------------------------------------------------------
# # OCR helper
# # ---------------------------------------------------------------------
# def _ocr(image_path: str) -> str:
#     if not OCR_AVAILABLE:
#         return ""
#     try:
#         img = Image.open(image_path)
#         text = pytesseract.image_to_string(img)
#         return text or ""
#     except Exception as e:
#         logger.debug("OCR failed: %s", e)
#         return ""


# # ---------------------------------------------------------------------
# # VALIDATOR AGENT (Robust)
# # ---------------------------------------------------------------------
# class ValidatorAgent:
#     # Sensible starting thresholds (tune as needed)
#     TYPE_REGION_THRESHOLD = 6.0
#     CLICK_REGION_THRESHOLD = 8.0
#     NAVIGATION_GLOBAL_THRESHOLD = 12.0
#     GLOBAL_FALLBACK_THRESHOLD = 6.0
#     DETECTION_CONFIDENCE_MIN = 0.25

#     def validate_step_yaml(self, exec_yaml: str) -> str:
#         """
#         exec_yaml expected structure (as produced by ExecutorAgent.run_step_yaml):
#         {
#             "step": {...},
#             "execution": {"status": "...", "before": path, "after": path, ...},
#             "validation": {...}
#         }
#         """
#         import yaml
#         data = yaml.safe_load(exec_yaml)

#         step = data.get("step", {})
#         exe = data.get("execution", {})

#         desc = (step.get("description") or "").lower()
#         before = exe.get("before")
#         after = exe.get("after")
#         status = exe.get("status")

#         # 0) Executor reported failure -> fail immediately
#         if status == "failed":
#             return yaml.safe_dump({"validation_status": "fail", "details": {"reason": "executor_failed", "error": exe.get("error")}})

#         # 1) no screenshot or executor signaled no_bbox -> fail
#         if status == "no_bbox" or not before or not after or not os.path.exists(before) or not os.path.exists(after):
#             return yaml.safe_dump({"validation_status": "fail", "details": {"reason": "missing_screenshots_or_no_bbox", "status": status}})

#         # Compute some diffs
#         # For typing actions we prefer OCR-based validation
#         if "type" in desc:
#             import re
#             m = re.search(r"['\"]([^'\"]+)['\"]", desc)
#             expected = m.group(1) if m else ""

#             # OCR verification (preferred)
#             if OCR_AVAILABLE and expected:
#                 ocr_after = _ocr(after).lower()
#                 # If exact expected appears in OCR text -> success (but check wrong-field detection)
#                 if expected.lower() in ocr_after:
#                     # WRONG FIELD DETECTION:
#                     # If typed text appears but it looks like part of an address bar (contains 'http' or 'google.com/search')
#                     if "http" in ocr_after or "google.com/search" in ocr_after or "search?q=" in ocr_after:
#                         return yaml.safe_dump({
#                             "validation_status": "fail",
#                             "details": {
#                                 "reason": "typed_in_wrong_input_field (likely omnibox)",
#                                 "ocr_excerpt": ocr_after[:400]
#                             }
#                         })
#                     return yaml.safe_dump({
#                         "validation_status": "pass",
#                         "details": {"method": "ocr", "matched": expected}
#                     })
#                 else:
#                     # OCR did not find expected text -> fallback to pixel region diff
#                     # region threshold tuned for typing
#                     region_diff = _pixel_diff_values(before, after)
#                     return yaml.safe_dump({
#                         "validation_status": "pass" if region_diff > self.TYPE_REGION_THRESHOLD else "fail",
#                         "details": {"method": "pixel_fallback", "diff": region_diff, "ocr_excerpt": ocr_after[:300]}
#                     })

#             # No OCR available or no expected text -> fallback to pixel diff
#             region_diff = _pixel_diff_values(before, after)
#             return yaml.safe_dump({
#                 "validation_status": "pass" if region_diff > self.TYPE_REGION_THRESHOLD else "fail",
#                 "details": {"method": "pixel", "diff": region_diff}
#             })

#         # ENTER = navigation: prefer a larger global diff (page navigation)
#         if "press enter" in desc or desc == "enter" or "navigate" in desc:
#             global_diff = _pixel_diff_values(before, after)
#             return yaml.safe_dump({
#                 "validation_status": "pass" if global_diff > self.NAVIGATION_GLOBAL_THRESHOLD else "fail",
#                 "details": {"reason": "navigation_change", "diff": global_diff}
#             })

#         # CLICK = expect local change near bbox if bbox provided
#         if "click" in desc or "double click" in desc or "right click" in desc:
#             # try to use bbox area if executor provided it
#             bbox = exe.get("bbox")
#             if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
#                 x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
#                 # compute a crop box slightly bigger than bbox
#                 pad = max(12, int(max(10, min(w, h) * 0.6)))
#                 crop_box = (int(x - pad), int(y - pad), int(x + w + pad), int(y + h + pad))
#                 region_diff = _pixel_diff_values(before, after, box=crop_box)
#                 if region_diff > self.CLICK_REGION_THRESHOLD:
#                     return yaml.safe_dump({"validation_status": "pass", "details": {"method": "pixel_region", "diff": region_diff}})
#                 # fallback to global diff
#                 global_diff = _pixel_diff_values(before, after)
#                 return yaml.safe_dump({"validation_status": "pass" if global_diff > self.GLOBAL_FALLBACK_THRESHOLD else "fail", "details": {"method": "global_pixel_fallback", "diff": global_diff, "region_diff": region_diff}})
#             else:
#                 # no bbox -> rely on global diff
#                 global_diff = _pixel_diff_values(before, after)
#                 return yaml.safe_dump({"validation_status": "pass" if global_diff > self.GLOBAL_FALLBACK_THRESHOLD else "fail", "details": {"method": "global_pixel", "diff": global_diff}})

#         # DEFAULT: accept if some visible change occurred
#         global_diff = _pixel_diff_values(before, after)
#         return yaml.safe_dump({"validation_status": "pass" if global_diff > 1.0 else "fail", "details": {"method": "pixel", "diff": global_diff}})
