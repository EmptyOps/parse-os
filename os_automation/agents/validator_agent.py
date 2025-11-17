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
import time

logger = logging.getLogger(__name__)

try:
    import cv2
except Exception:
    cv2 = None


class ValidatorAgent:
    """
    Primary validator: uses pixel-diff fraction (existing behavior).
    Optionally does a micro-region diff and grounding re-check if available.
    """

    def __init__(self, diff_threshold: float = 0.01, micro_region_size: int = 50):
        self.diff_threshold = diff_threshold
        self.micro_region_size = micro_region_size

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
            a = a.resize((w, h))
            b = b.resize((w, h))
            arr_a = np.array(a).astype(np.int32)
            arr_b = np.array(b).astype(np.int32)
            diff = np.abs(arr_a - arr_b)
            nonzero = np.sum(diff > 10)
            total = diff.size
            return float(nonzero) / float(total)
        except Exception as e:
            logger.debug("pixel diff failed: %s", e)
            return 0.0

    def _micro_region_diff(self, before_path: str, after_path: str, cx: int, cy: int) -> float:
        """
        Compute average absolute difference in a small region around cx,cy.
        Returns average absolute diff (0..255).
        """
        try:
            a = Image.open(before_path).convert("L")
            b = Image.open(after_path).convert("L")
            w, h = a.size
            box = (
                max(0, cx - self.micro_region_size),
                max(0, cy - self.micro_region_size),
                min(w, cx + self.micro_region_size),
                min(h, cy + self.micro_region_size),
            )
            a_crop = a.crop(box).resize((100, 100))
            b_crop = b.crop(box).resize((100, 100))
            arr_a = np.array(a_crop).astype(np.int32)
            arr_b = np.array(b_crop).astype(np.int32)
            diff = np.abs(arr_a - arr_b)
            avg = float(np.mean(diff))
            return avg
        except Exception as e:
            logger.debug("micro region diff failed: %s", e)
            return 0.0

    def validate_step(self, step: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        step: a dict with at least description
        exec_result: dict with before, after, raw (which may include bbox & decision)
        """
        before = exec_result.get("before")
        after = exec_result.get("after")
        raw = exec_result.get("raw") or {}
        bbox = raw.get("bbox")
        decision = raw.get("decision", {})

        if not before or not after or not os.path.exists(before) or not os.path.exists(after):
            return {"validation_status": "unknown", "reason": "no-screenshots", "details": {"before": before, "after": after}}

        try:
            # 1) Micro-region check (if bbox provided) -> helps with targeted changes
            micro = None
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                cx = int(bbox[0] + bbox[2] / 2)
                cy = int(bbox[1] + bbox[3] / 2)
                micro = self._micro_region_diff(before, after, cx, cy)
                # heuristic: micro-region average diff > 8 indicates change
                if micro and micro > 8:
                    frac = self._pixel_diff_fraction(before, after)
                    return {"validation_status": "pass", "details": {"micro_region_avg": micro, "pixel_change_fraction": frac}}

            # 2) Full-image pixel diff (existing robust check)
            frac = self._pixel_diff_fraction(before, after)
            passed = frac >= self.diff_threshold
            if passed:
                return {"validation_status": "pass", "details": {"pixel_change_fraction": frac}}

            # 3) Fallback: checksums (fast fallback)
            c1 = self._checksum(before)
            c2 = self._checksum(after)
            if c1 != c2:
                return {"validation_status": "pass", "details": {"checksum_before": c1, "checksum_after": c2}}

            # 4) Optionally: grounding re-check if raw contains info and a grounding adapter is registered.
            # This is conservative: only attempt if grounding adapter is present and returned a bbox earlier.
            try:
                if bbox:
                    # re-run the configured grounding adapter to see if target moved/disappeared.
                    from os_automation.core.registry import registry
                    det_factory = registry.get_adapter("osatlas") or registry.get_adapter("omniparser")
                    if det_factory:
                        det = det_factory() if callable(det_factory) else det_factory
                        # many adapters accept a payload {"image_path": path, "text": desc}
                        fresh_pos = None
                        try:
                            # try detect-like call
                            res = None
                            for fn in ("detect", "call", "run", "predict", "infer"):
                                if hasattr(det, fn):
                                    try:
                                        res = getattr(det, fn)({"image_path": after, "text": step.get("description")})
                                        break
                                    except Exception:
                                        continue
                            # parse typical responses
                            if isinstance(res, dict) and "bbox" in res:
                                bx = res["bbox"]
                                if len(bx) >= 2:
                                    p = _parse_position_like = None
                                    try:
                                        # midpoint parse
                                        x = int((bx[0] + (bx[2] if bx[2] > bx[0] else bx[0])) / 2)
                                        y = int((bx[1] + (bx[3] if bx[3] > bx[1] else bx[1])) / 2)
                                        fresh_pos = (x, y)
                                    except Exception:
                                        fresh_pos = None
                            # if the grounding no longer finds target -> assume success
                            if fresh_pos is None:
                                return {"validation_status": "pass", "details": {"reason": "grounding_missing_after_action"}}
                        except Exception:
                            # ignore grounding re-check errors
                            pass
            except Exception:
                pass

            # Nothing convinced us the UI changed
            return {"validation_status": "fail", "details": {"pixel_change_fraction": frac, "micro_region_avg": micro}}
        except Exception as e:
            logger.exception("Validation exception: %s", e)
            # Fallback to checksum comparison
            try:
                c1 = self._checksum(before)
                c2 = self._checksum(after)
                passed = c1 != c2
                return {"validation_status": "pass" if passed else "fail", "details": {"checksum_before": c1, "checksum_after": c2}}
            except Exception as e2:
                logger.debug("Final validation fallback failed: %s", e2)
                return {"validation_status": "unknown", "reason": str(e)}
