# os_automation/repos/osatlas_adapter.py

import os
import re
import json
import requests
import logging
from typing import Any, Dict, List, Optional
from PIL import Image

from os_automation.core.adapters import BaseAdapter
from os_automation.core.integration_contract import IntegrationMode

logger = logging.getLogger(__name__)


###############################################################
# 🔥 BUILT-IN HELPERS (NO NEW FILE, NO EXTERNAL IMPORTS)
###############################################################

def _parse_position_raw(pos) -> Optional[List[int]]:
    """
    Accepts MANY formats and extracts x,y from OS-Atlas weird responses.

    Supported:
    - [x, y]
    - [x1, y1, x2, y2]
    - ["123","456"]
    - "(123,456)"
    - "x=123, y=456"
    - "{ 'x':123 , 'y':456 }"
    - strings containing numbers
    """
    if pos is None:
        return None

    # -----------------------
    # Direct list input
    # -----------------------
    if isinstance(pos, (list, tuple)):
        nums = []
        for p in pos:
            try:
                nums.append(float(p))
            except:
                pass

        if len(nums) == 2:
            return [int(nums[0]), int(nums[1])]

        if len(nums) >= 4:
            x1, y1, x2, y2 = nums[:4]
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            return [int(cx), int(cy)]

        return None

    # -----------------------
    # JSON string
    # -----------------------
    if isinstance(pos, str):
        s = pos.strip()

        # try JSON decode
        try:
            v = json.loads(s)
            if isinstance(v, (list, tuple)):
                return _parse_position_raw(v)
        except:
            pass

        # regex: find two numbers
        m = re.search(r"(-?\d{1,5})\D+(-?\d{1,5})", s)
        if m:
            return [int(m.group(1)), int(m.group(2))]

    return None


def normalize_coordinates(coords: List[int], image_path: str) -> List[int]:
    """
    Ensures x,y are inside image size.
    """
    try:
        img = Image.open(image_path)
        W, H = img.size
    except:
        return coords

    x, y = coords
    x = max(0, min(W - 1, int(x)))
    y = max(0, min(H - 1, int(y)))
    return [x, y]


from PIL import ImageDraw

def draw_big_dot(image: Image.Image, point, color="red"):
    """
    Simple helper to draw a big debugging dot (like sandbox_agent).
    """
    x, y = point
    draw = ImageDraw.Draw(image)
    r = 8
    draw.ellipse([x-r, y-r, x+r, y+r], fill=color)
    return image



###############################################################
# 🔥 OS-ATLAS ADAPTER (SELF-CONTAINED + IMPROVED)
###############################################################

class OSAtlasAdapter(BaseAdapter):
    """
    Unified & enhanced OS-Atlas adapter:

    ✔ Uses your existing /predict endpoint
    ✔ Parses xyxy properly
    ✔ Repairs malformed bbox automatically
    ✔ Falls back to center-point detection
    ✔ Normalizes bounding boxes
    ✔ Returns ALWAYS a valid [x,y,w,h]
    """

    integration_mode = IntegrationMode.PARTIAL
    capabilities = ["detect"]

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get(
            "OSATLAS_URL",
            "http://localhost:8000/predict"
        )

    # ---------------------------------------------------------
    # API CALL (unchanged from your business logic)
    # ---------------------------------------------------------
    def _call_predict(self, image_path: str, text: str = "") -> Dict[str, Any]:
        url = self.base_url
        files = {}
        data = {"text": text}

        if image_path and os.path.exists(image_path):
            files["image"] = open(image_path, "rb")
        else:
            raise FileNotFoundError(f"Image not found at {image_path}")

        try:
            resp = requests.post(url, files=files, data=data, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.exception("OS-Atlas call failed: %s", e)
            return {"error": str(e)}
        finally:
            for f in files.values():
                try: f.close()
                except: pass

    
    # ---------------------------------------------------------
    # MAIN DETECT LOGIC (IMPROVED, NO REFERENCE REPO CODE)
    # ---------------------------------------------------------
    def detect(self, step: Dict[str, Any]) -> Dict[str, Any]:
        image_path = step.get("image_path")
        text_query = (step.get("text", step.get("description", "")) or "").strip()

        if not image_path or not os.path.exists(image_path):
            logger.warning("OSAtlasAdapter.detect: missing image_path %s", image_path)
            return {
                "bbox": None, "point": None, "confidence": 0.0,
                "raw": {}, "type": "none"
            }

        # ------------------------------------------
        # 1) CALL OS-ATLAS
        # ------------------------------------------
        resp = self._call_predict(image_path, text_query)
        raw_response = (
            resp.get("response")
            or resp.get("bbox")
            or resp.get("raw_output")
            or resp.get("predictions")
            or resp.get("result")
            or resp
        )

        # helper to parse xyxy or point
        def _parse_xyxy(raw):
            if isinstance(raw, (list, tuple)) and len(raw) >= 4:
                return [float(v) for v in raw[:4]]
            if isinstance(raw, dict):
                for kset in (("x1","y1","x2","y2"),("left","top","right","bottom")):
                    if all(k in raw for k in kset):
                        return [float(raw[k]) for k in kset]
            if isinstance(raw, str):
                nums = re.findall(r"-?\d{1,6}", raw)
                if len(nums) >= 4:
                    return [float(nums[0]), float(nums[1]), float(nums[2]), float(nums[3])]
            return None

        xyxy = _parse_xyxy(raw_response)
        conf = float(resp.get("confidence", 0.0))

        # ------------------------------------------
        # 2) OSATLAS valid result
        # ------------------------------------------
        if xyxy and conf >= 0.42:
            x1, y1, x2, y2 = xyxy
            left, top = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            left, top = normalize_coordinates([left, top], image_path)

            bbox = [int(left), int(top), int(max(1, w)), int(max(1, h))]
            return {
                "bbox": bbox,
                "point": [bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2],
                "confidence": conf,
                "raw": resp,
                "type": "osatlas_bbox"
            }

        # ------------------------------------------
        # 3) FALLBACK: TEXT-BASED OCR SEARCH
        # (your architecture already uses OCR in validator)
        # ------------------------------------------
        try:
            from os_automation.tools.ocr import simple_ocr
            ocr_text, word_boxes = simple_ocr(image_path)
        except:
            ocr_text, word_boxes = ("", [])

        # try match query inside OCR-words
        if text_query and word_boxes:
            matches = [
                box for (word, box) in word_boxes
                if text_query.lower() in word.lower()
            ]
            if matches:
                # use first match
                x, y, w, h = matches[0]
                return {
                    "bbox": [x, y, w, h],
                    "point": [x + w//2, y + h//2],
                    "confidence": 0.30,
                    "raw": resp,
                    "type": "ocr_text_match"
                }

        # ------------------------------------------
        # 4) FINAL FALLBACK → CENTER OF SCREEN
        # ------------------------------------------
        from PIL import Image
        img = Image.open(image_path)
        W, H = img.size
        cx, cy = W//2, H//2
        bbox = [cx - 40, cy - 40, 80, 80]

        logger.warning("OSAtlasAdapter: fallback to center for query '%s'", text_query)

        return {
            "bbox": bbox,
            "point": [cx, cy],
            "confidence": 0.0,
            "raw": resp,
            "type": "center_fallback"
        }



    # ---------------------------------------------------------
    # You said KEEP BUSINESS LOGIC → DO NOT REMOVE
    # ---------------------------------------------------------
    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "no-op", "reason": "osatlas adapter only supports detection"}

    def validate(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return {"validation": "unknown", "reason": "not implemented"}


# For registry
def create():
    return OSAtlasAdapter()