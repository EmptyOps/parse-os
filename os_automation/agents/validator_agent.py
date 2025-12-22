# os_automation/agents/validator_agent.py

import os
import logging
import base64
import io
from typing import Dict, Any, Optional

from PIL import Image, ImageChops, ImageStat

from openai import OpenAI

logger = logging.getLogger(__name__)

# Try OCR
try:
    import pytesseract

    OCR_AVAILABLE = True
except Exception:
    pytesseract = None
    OCR_AVAILABLE = False
    logger.debug("pytesseract not available; using pixel diff only.")


def _pixel_diff(before_path: str, after_path: str) -> float:
    try:
        if not (before_path and after_path):
            return 0.0
        if not os.path.exists(before_path) or not os.path.exists(after_path):
            return 0.0

        b1 = Image.open(before_path).convert("RGB")
        b2 = Image.open(after_path).convert("RGB")

        # downsample to make diff more stable and cheap
        b1 = b1.resize((max(1, b1.width // 2), max(1, b1.height // 2)))
        b2 = b2.resize((max(1, b2.width // 2), max(1, b2.height // 2)))

        diff = ImageChops.difference(b1, b2)
        stat = ImageStat.Stat(diff)
        mean_val = sum(stat.mean) / len(stat.mean)
        return mean_val
    except Exception as e:
        logger.exception("pixel diff error: %s", e)
        return 0.0


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


class ValidatorAgent:
    """
    Validates each step using:
      - pixel diff
      - OCR (when available)
      - optional LLM text-based decision for ambiguous cases
    """

    # These thresholds are in mean 0–255 per pixel space
    # TYPE_THRESHOLD = 2.0
    # CLICK_THRESHOLD = 5.0
    # NAVIGATION_THRESHOLD = 5.0
    
    TYPE_THRESHOLD = 0.8
    CLICK_THRESHOLD = 1.2
    NAVIGATION_THRESHOLD = 1.5


    def __init__(self):
        self.llm_client: Optional[OpenAI] = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                self.llm_client = OpenAI(api_key=api_key)
            except Exception as e:
                logger.debug("ValidatorAgent: failed to init OpenAI client: %s", e)

    # ========================= LLM Helpers =========================
    def _encode_small_preview(
        self,
        image_path: str,
        max_size=(600, 400),
        max_bytes: int = 50_000,
    ) -> str:
        try:
            if not image_path or not os.path.exists(image_path):
                return ""
            img = Image.open(image_path).convert("RGB")
            img.thumbnail(max_size)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            b = buf.getvalue()
            if len(b) > max_bytes:
                b = b[:max_bytes]
            return base64.b64encode(b).decode("ascii")
        except Exception as e:
            logger.debug("preview encode failed: %s", e)
            return ""

    def _llm_validation_decision(
        self,
        step_desc: str,
        event_hint: str,
        diff: float,
        ocr_excerpt: str = "",
    ) -> Optional[bool]:
        """
        Ask LLM to break ties only when there IS some change but it's below
        our strict pixel thresholds.
        """
        if not self.llm_client:
            return None
        try:
            system_msg = (
                "You are a strict OS automation validator. Given a step description, "
                "a numeric pixel diff, and optional OCR excerpt, decide if the step "
                "likely succeeded. Reply ONLY 'pass' or 'fail'."
            )
            user_msg = (
                f"Step description: {step_desc}\n"
                f"Event type: {event_hint}\n"
                f"Pixel diff value: {diff:.4f}\n"
                f"OCR excerpt after step: {ocr_excerpt[:200]}\n\n"
                "Respond 'pass' if the change matches, otherwise 'fail'."
            )

            resp = self.llm_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=5,
            )
            answer = (resp.choices[0].message.content or "").strip().lower()
            if answer.startswith("pass"):
                return True
            if answer.startswith("fail"):
                return False
        except Exception as e:
            logger.debug("LLM validation failed: %s", e)
        return None

    # ========================= YAML Entry =========================
    def validate_step_yaml(self, exec_yaml: str) -> str:
        import yaml

        try:
            data = yaml.safe_load(exec_yaml) or {}
        except Exception:
            return yaml.safe_dump(
                {
                    "validation_status": "fail",
                    "details": {"reason": "invalid_exec_yaml"},
                }
            )

        step = data.get("step", {})
        exe = data.get("execution", {})

        desc = (step.get("description") or "").lower()
        before = exe.get("before")
        after = exe.get("after")

        if exe.get("status") == "failed":
            return yaml.safe_dump(
                {"validation_status": "fail", "details": {"reason": "executor_failed"}}
            )

        if not before or not after or not os.path.exists(before) or not os.path.exists(
            after
        ):
            return yaml.safe_dump(
                {
                    "validation_status": "fail",
                    "details": {"reason": "missing_screenshots"},
                }
            )

        diff = _pixel_diff(before, after)
        
        # ===== LOCAL REGION DIFF (BBOX-LEVEL CHANGE CHECK) =====
        bbox = exe.get("bbox")
        if bbox and len(bbox) >= 4:
            try:
                x, y, w, h = [int(v) for v in bbox[:4]]

                B = Image.open(before).convert("RGB")
                A = Image.open(after).convert("RGB")

                # Crop expanded region to capture UI reaction (hover, highlight, focus)
                pad = 18
                region = (
                    max(0, x - pad), 
                    max(0, y - pad), 
                    min(B.width, x + w + pad),
                    min(B.height, y + h + pad)
                )

                Bc = B.crop(region)
                Ac = A.crop(region)

                # local mean difference
                local_diff = ImageStat.Stat(ImageChops.difference(Bc, Ac)).mean
                local_diff = sum(local_diff) / len(local_diff)

                if local_diff > 1.0:
                    return yaml.safe_dump({
                        "validation_status": "pass",
                        "details": {
                            "method": "local_region_diff",
                            "local_diff": float(local_diff),
                            "global_diff": float(diff)
                        }
                    })
            except Exception as e:
                logger.debug("local region diff failed: %s", e)


        # Special-case "first search result" type clicks – still allow some optimism
        if any(
            k in desc
            for k in (
                "first search result",
                "first result",
                "first link",
                "open first result",
            )
        ):
            return yaml.safe_dump(
                {
                    "validation_status": "pass",
                    "details": {
                        "method": "special_case",
                        "reason": "first_search_result_click_assumed_ok",
                        "diff": diff,
                    },
                }
            )

        import re

        is_type_step = desc.startswith("type ") or "type '" in desc
        is_run_cmd_step = "run command" in desc
        looks_like_terminal = is_run_cmd_step or "terminal" in desc or "shell" in desc

        # ===================== Typing / Run Command =====================
        if is_type_step or is_run_cmd_step:
            m = re.search(r"['\"](.+?)['\"]", step.get("description", ""))
            expected = (m.group(1) if m else "").strip()
            ocr_after = _ocr(after).lower() if OCR_AVAILABLE else ""

            # Exact OCR match if available
            if expected and expected.lower() in ocr_after:
                return yaml.safe_dump(
                    {
                        "validation_status": "pass",
                        "details": {"method": "ocr", "matched": expected, "diff": diff},
                    }
                )

            # Terminal: content just changed somehow
            if looks_like_terminal:
                if ocr_after.strip():
                    return yaml.safe_dump(
                        {
                            "validation_status": "pass",
                            "details": {
                                "method": "ocr_terminal_heuristic",
                                "ocr_excerpt": ocr_after[:200],
                                "diff": diff,
                            },
                        }
                    )

                # Pixel-based decision
                status = "pass" if diff > self.TYPE_THRESHOLD else "fail"
                details: Dict[str, Any] = {
                    "method": "pixel_terminal",
                    "diff": diff,
                    "threshold": self.TYPE_THRESHOLD,
                }

                # Use LLM only when diff is non-zero but below threshold
                if status == "fail" and diff > 0.5:
                    llm_decision = self._llm_validation_decision(
                        step.get("description", ""),
                        "terminal_type_or_run",
                        diff,
                        ocr_after[:200],
                    )
                    if llm_decision is True:
                        status = "pass"
                        details["llm_override"] = True
                    elif llm_decision is False:
                        details["llm_confirmation"] = "fail"

                return yaml.safe_dump(
                    {"validation_status": status, "details": details}
                )

            # Non-terminal typing
            status = "pass" if diff > self.TYPE_THRESHOLD else "fail"
            details: Dict[str, Any] = {
                "method": "pixel_typing",
                "diff": diff,
                "threshold": self.TYPE_THRESHOLD,
            }
            if status == "fail" and diff > 0.5:
                llm_decision = self._llm_validation_decision(
                    step.get("description", ""),
                    "typing",
                    diff,
                    "",
                )
                if llm_decision is True:
                    status = "pass"
                    details["llm_override"] = True
                elif llm_decision is False:
                    details["llm_confirmation"] = "fail"
            return yaml.safe_dump({"validation_status": status, "details": details})

        # ===================== Press Enter / Navigation =====================
        if "press enter" in desc or desc == "enter":
            ocr_after = _ocr(after).lower() if OCR_AVAILABLE else ""
            # GNOME rule → Enter passes ONLY if content changed
            if diff > 2.5 or len(ocr_after) > 0:
                return yaml.safe_dump(
                    {"validation_status": "pass",
                    "details": {"diff": diff, "ocr_excerpt": ocr_after[:200]}}
                )
            return yaml.safe_dump(
                {"validation_status": "fail",
                "details": {"reason": "enter_no_effect", "diff": diff}}
            )

        # ===================== Special Search Box / Omnibox =====================
        # if any(
        #     k in desc for k in ("click search box", "search box", "click address bar")
        # ):
        #     return yaml.safe_dump(
        #         {
        #             "validation_status": "pass",
        #             "details": {
        #                 "method": "special_case",
        #                 "reason": "google_search_box_clicked",
        #                 "diff": diff,
        #             },
        #         }
        #     )

        # ===================== Generic Click =====================
        if "click" in desc or "double click" in desc or "right click" in desc:
            ocr_after = _ocr(after).lower() if OCR_AVAILABLE else ""
            # status = "pass" if diff > self.CLICK_THRESHOLD else "fail"
            # try global diff
            if diff > self.CLICK_THRESHOLD or diff > 0.5:
                status = "pass"
            else:
                # fallback to local diff we computed earlier
                if 'local_diff' in locals() and local_diff > 0.8:
                    status = "pass"
                else:
                    status = "fail"

            details: Dict[str, Any] = {
                "method": "pixel",
                "diff": diff,
                "threshold": self.CLICK_THRESHOLD,
            }
            if status == "fail" and diff > 0.5:
                llm_decision = self._llm_validation_decision(
                    step.get("description", ""), "click", diff, ocr_after[:200]
                )
                if llm_decision is True:
                    status = "pass"
                    details["llm_override"] = True
                elif llm_decision is False:
                    details["llm_confirmation"] = "fail"
            return yaml.safe_dump({"validation_status": status, "details": details})

        # ===================== Default: any other change =====================
        status = "pass" if diff > self.NAVIGATION_THRESHOLD else "fail"
        details: Dict[str, Any] = {
            "method": "pixel_default",
            "diff": diff,
            "threshold": self.NAVIGATION_THRESHOLD,
        }
        if status == "fail" and diff > 0.5:
            ocr_after = _ocr(after).lower() if OCR_AVAILABLE else ""
            llm_decision = self._llm_validation_decision(
                step.get("description", ""), "default", diff, ocr_after[:200]
            )
            if llm_decision is True:
                status = "pass"
                details["llm_override"] = True
            elif llm_decision is False:
                details["llm_confirmation"] = "fail"

        import yaml as _yaml

        return _yaml.safe_dump(
            {"validation_status": status, "details": details}
        )

    # ----------------------------------------------------------------
    # Optional: Advanced validator (kept as-is for compatibility)
    # ----------------------------------------------------------------
    def validate_step_advanced(
        self,
        description: str,
        before_path: str,
        after_path: str,
        bbox,
    ):
        import numpy as np

        desc = description.lower()
        if not before_path or not after_path:
            return {"valid": False, "reason": "missing_screenshots"}
        if not os.path.exists(before_path) or not os.path.exists(after_path):
            return {"valid": False, "reason": "missing_files"}

        before_img = Image.open(before_path).convert("L")
        after_img = Image.open(after_path).convert("L")
        bw, bh = before_img.size

        # local region compare
        try:
            x, y, w, h = bbox or [0, 0, 50, 50]
            pad = 40
            region = (
                max(0, x - pad),
                max(0, y - pad),
                min(bw, x + w + pad),
                min(bh, y + h + pad),
            )
            before_crop = before_img.crop(region)
            after_crop = after_img.crop(region)
            diff_local = np.mean(
                np.abs(
                    np.array(before_crop, dtype=np.int16)
                    - np.array(after_crop, dtype=np.int16)
                )
            )
            if diff_local > 12:
                return {
                    "valid": True,
                    "reason": "local_difference_detected",
                    "diff_local": float(diff_local),
                }
        except Exception:
            pass

        # global diff
        try:
            diff_global = np.mean(
                np.abs(
                    np.array(before_img, dtype=np.int16)
                    - np.array(after_img, dtype=np.int16)
                )
            )
            if diff_global > 6:
                return {
                    "valid": True,
                    "reason": "global_change_detected",
                    "diff_global": float(diff_global),
                }
        except Exception:
            pass

        # OCR-based fallback
        if OCR_AVAILABLE:
            try:
                text_after = _ocr(after_path).lower()
                if any(tok in text_after for tok in desc.split()):
                    return {
                        "valid": True,
                        "reason": "ocr_matched",
                        "excerpt": text_after[:200],
                    }
            except Exception:
                pass

        # bbox region diff
        try:
            x, y, w, h = bbox or [0, 0, 50, 50]
            bx1 = before_img.crop((x, y, x + w, y + h))
            bx2 = after_img.crop((x, y, x + w, y + h))
            diff_bbox = np.mean(
                np.abs(
                    np.array(bx1, dtype=np.int16) - np.array(bx2, dtype=np.int16)
                )
            )
            if diff_bbox > 10:
                return {
                    "valid": True,
                    "reason": "bbox_state_changed",
                    "diff_bbox": float(diff_bbox),
                }
        except Exception:
            pass

        return {"valid": False, "reason": "no_state_change_detected"}
