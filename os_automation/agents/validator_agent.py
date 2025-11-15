# # os_automation/agents/validator_agent.py
# import os
# import hashlib
# import logging
# from typing import Dict, Any
# from os_automation.core.tal import ExecutionResult

# logger = logging.getLogger(__name__)

# # optional cv2
# try:
#     import cv2
#     import numpy as np
# except Exception:
#     cv2 = None
#     np = None

# class ValidatorAgent:
#     """
#     Validate a single step by comparing before/after screenshots.
#     - If OpenCV available, compute normalized diff fraction and use threshold.
#     - Otherwise fall back to byte-checksum comparison.
#     """

#     def __init__(self, diff_threshold: float = 0.01):
#         # If > threshold changed -> consider PASS (since action should change UI)
#         # NOTE: tweak as needed: 0.01 means 1% pixel change
#         self.diff_threshold = diff_threshold

#     def _checksum(self, path: str) -> str:
#         h = hashlib.sha256()
#         with open(path, "rb") as f:
#             for chunk in iter(lambda: f.read(8192), b""):
#                 h.update(chunk)
#         return h.hexdigest()

#     def _pixel_diff_fraction(self, a_path: str, b_path: str) -> float:
#         if not cv2:
#             raise RuntimeError("OpenCV not available")
#         a = cv2.imread(a_path)
#         b = cv2.imread(b_path)
#         if a is None or b is None:
#             return 0.0
#         # resize to smallest common size for safe comparison
#         h = min(a.shape[0], b.shape[0])
#         w = min(a.shape[1], b.shape[1])
#         a_s = cv2.resize(a, (w, h))
#         b_s = cv2.resize(b, (w, h))
#         diff = cv2.absdiff(a_s, b_s)
#         gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
#         nonzero = (gray > 10).sum()  # threshold small pixel noise
#         total = gray.size
#         return float(nonzero) / float(total)

#     def validate_step(self, step: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         step: planned step dict
#         exec_result: ExecutionResult.dict() or executor return
#         Returns: {"validation_status":"pass"|"fail"|"unknown", "details": {...}}
#         """
#         before = exec_result.get("screenshot_before") or exec_result.get("before") or (exec_result.get("raw") or {}).get("before")
#         after = exec_result.get("screenshot_after") or exec_result.get("after") or (exec_result.get("raw") or {}).get("after")

#         # if none available, unknown
#         if not before or not after or not os.path.exists(before) or not os.path.exists(after):
#             return {"validation_status": "unknown", "reason": "no-screenshots", "details": {"before": before, "after": after}}

#         try:
#             if cv2:
#                 frac = self._pixel_diff_fraction(before, after)
#                 passed = frac >= self.diff_threshold
#                 return {"validation_status": "pass" if passed else "fail", "details": {"pixel_change_fraction": frac}}
#             else:
#                 # fallback: checksum changed -> PASS
#                 c1 = self._checksum(before)
#                 c2 = self._checksum(after)
#                 passed = c1 != c2
#                 return {"validation_status": "pass" if passed else "fail", "details": {"checksum_before": c1, "checksum_after": c2}}
#         except Exception as e:
#             logger.exception("Validation failed: %s", e)
#             return {"validation_status": "unknown", "reason": str(e)}


# os_automation/agents/validator_agent.py
import os
import hashlib
import logging
from typing import Dict, Any
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
except Exception:
    cv2 = None

class ValidatorAgent:
    def __init__(self, diff_threshold: float = 0.01):
        self.diff_threshold = diff_threshold

    def _checksum(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _pixel_diff_fraction(self, a_path: str, b_path: str) -> float:
        try:
            a = Image.open(a_path).convert("L")
            b = Image.open(b_path).convert("L")
            # convert to same size
            w = min(a.size[0], b.size[0])
            h = min(a.size[1], b.size[1])
            a = a.resize((w,h))
            b = b.resize((w,h))
            arr_a = np.array(a).astype(np.int32)
            arr_b = np.array(b).astype(np.int32)
            diff = np.abs(arr_a - arr_b)
            nonzero = np.sum(diff > 10)
            total = diff.size
            return float(nonzero) / float(total)
        except Exception as e:
            logger.debug("pixel diff failed: %s", e)
            return 0.0

    def validate_step(self, step: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        before = exec_result.get("before")
        after = exec_result.get("after")
        if not before or not after or not os.path.exists(before) or not os.path.exists(after):
            return {"validation_status":"unknown", "reason":"no-screenshots", "details":{"before":before,"after":after}}

        try:
            # try small-region first: if region around center changed -> pass quickly
            frac = self._pixel_diff_fraction(before, after)
            passed = frac >= self.diff_threshold
            return {"validation_status":"pass" if passed else "fail", "details":{"pixel_change_fraction": frac}}
        except Exception as e:
            logger.exception("Validation exception: %s", e)
            # fallback to checksum
            c1 = self._checksum(before)
            c2 = self._checksum(after)
            passed = c1 != c2
            return {"validation_status":"pass" if passed else "fail", "details":{"checksum_before": c1, "checksum_after": c2}}
