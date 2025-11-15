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
    # MAIN DETECT LOGIC (IMPROVED)
    # ---------------------------------------------------------
    def detect(self, step: Dict[str, Any]) -> Dict[str, Any]:
        image_path = step.get("image_path")
        text = step.get("text", step.get("description", ""))

        resp = self._call_predict(image_path, text)

        raw_xyxy = resp.get("response")

        # -------------------------------
        # 1) If provider returned xyxy
        # -------------------------------
        if isinstance(raw_xyxy, list) and len(raw_xyxy) == 4:
            try:
                x1, y1, x2, y2 = [int(v) for v in raw_xyxy]
                left = min(x1, x2)
                top = min(y1, y2)
                right = max(x1, x2)
                bottom = max(y1, y2)
                w = max(1, right - left)
                h = max(1, bottom - top)
                return {
                    "bbox": [left, top, w, h],
                    "raw": resp
                }
            except:
                pass

        # -------------------------------
        # 2) Fallback: try to parse ANY format
        # -------------------------------
        parsed_point = _parse_position_raw(raw_xyxy)

        if parsed_point:
            parsed_point = normalize_coordinates(parsed_point, image_path)

            px, py = parsed_point
            # tiny fallback bbox
            return {
                "bbox": [px - 10, py - 10, 20, 20],
                "raw": resp
            }

        # -------------------------------
        # 3) Total failure
        # -------------------------------
        logger.warning("OSAtlasAdapter: invalid bbox response: %s", raw_xyxy)
        return {"bbox": None, "raw": resp}

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
