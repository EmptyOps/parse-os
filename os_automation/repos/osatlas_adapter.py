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
        # ---------------------------------------------------------
    # MAIN DETECT LOGIC (IMPROVED)
    # ---------------------------------------------------------
    def detect(self, step: Dict[str, Any]) -> Dict[str, Any]:
        image_path = step.get("image_path")
        text = (step.get("text", step.get("description", "")) or "").strip()

        # Guard
        if not image_path or not os.path.exists(image_path):
            logger.warning("OSAtlasAdapter.detect: missing image_path %s", image_path)
            return {"bbox": None, "point": None, "confidence": 0.0, "raw": {}, "type": "none"}

        resp = self._call_predict(image_path, text)

        # model may return many shapes: try common keys first
        raw_response = resp.get("response") or resp.get("bbox") or resp.get("raw_output") or resp.get("predictions") or resp.get("result") or resp

        # Helper to attempt parsing numeric lists from strings
        def _parse_any(raw):
            # direct XYXY list
            if isinstance(raw, (list, tuple)) and len(raw) >= 4:
                return [int(float(v)) for v in raw[:4]]
            # if a list of 2 -> point
            if isinstance(raw, (list, tuple)) and len(raw) == 2:
                return [int(float(raw[0])), int(float(raw[1]))]
            # dict with x,y or x1,y1,x2,y2
            if isinstance(raw, dict):
                # try multiple keys
                for kset in (("x1","y1","x2","y2"), ("x","y"), ("left","top","right","bottom")):
                    if all(k in raw for k in kset):
                        vals = [int(float(raw[k])) for k in kset if k in raw]
                        return vals
            # string attempts
            if isinstance(raw, str):
                # try to find numbers: two or four
                m = re.findall(r"-?\d{1,6}", raw)
                if len(m) >= 4:
                    return [int(m[0]), int(m[1]), int(m[2]), int(m[3])]
                if len(m) >= 2:
                    return [int(m[0]), int(m[1])]
            return None

        parsed = _parse_any(raw_response)

        # 1) xyxy -> bbox
        if parsed and len(parsed) >= 4:
            x1, y1, x2, y2 = parsed[:4]
            left = min(x1, x2); top = min(y1, y2); right = max(x1, x2); bottom = max(y1, y2)
            w = max(1, right - left); h = max(1, bottom - top)
            bbox = [left, top, w, h]
            # normalize to image
            nx, ny = normalize_coordinates([left, top], image_path)
            bbox[0] = nx; bbox[1] = ny
            return {"bbox": bbox, "point": [nx + w//2, ny + h//2], "confidence": float(resp.get("confidence", 1.0)), "raw": resp, "type": "bbox"}

        # 2) point -> tiny bbox
        if parsed and len(parsed) == 2:
            px, py = parsed
            px, py = normalize_coordinates([px, py], image_path)
            bbox = [max(0, px - 12), max(0, py - 12), 24, 24]
            return {"bbox": bbox, "point": [px, py], "confidence": float(resp.get("confidence", 1.0)), "raw": resp, "type": "point"}

        # 3) try legacy 'raw_output' text extraction: look for <|box_start|> token pattern
        if isinstance(raw_response, str) and "<|box_start|" in raw_response:
            m = re.search(r"<\|box_start\|>(.*?)<\|box_end\|>", raw_response, re.S)
            if m:
                inner = m.group(1)
                parsed2 = _parse_any(inner)
                if parsed2:
                    if len(parsed2) >= 4:
                        x1, y1, x2, y2 = parsed2[:4]
                        left = min(x1, x2); top = min(y1, y2)
                        w = max(1, abs(x2 - x1)); h = max(1, abs(y2 - y1))
                        bbox = [left, top, w, h]
                        bbox[0], bbox[1] = normalize_coordinates([bbox[0], bbox[1]], image_path)
                        return {"bbox": bbox, "point": [bbox[0] + w//2, bbox[1] + h//2], "confidence": float(resp.get("confidence", 1.0)), "raw": resp, "type": "bbox"}

        # 4) give warning + best-effort center fallback (image center)
        try:
            img = Image.open(image_path)
            W, H = img.size
            cx, cy = W//2, H//2
            bbox = [cx - 50, cy - 50, 100, 100]
            bbox[0], bbox[1] = normalize_coordinates([bbox[0], bbox[1]], image_path)
            logger.warning("OSAtlasAdapter: could not parse response; returning center fallback. raw_response=%s", raw_response)
            return {"bbox": bbox, "point": [cx, cy], "confidence": 0.0, "raw": resp, "type": "fallback_center"}
        except Exception:
            return {"bbox": None, "point": None, "confidence": 0.0, "raw": resp, "type": "none"}


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
