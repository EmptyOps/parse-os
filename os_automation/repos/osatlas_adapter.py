# os_automation/repos/osatlas_adapter.py
import os
import requests
from typing import Any, Dict
from os_automation.core.adapters import BaseAdapter
from os_automation.core.integration_contract import IntegrationMode
from PIL import Image

class OSAtlasAdapter(BaseAdapter):
    """
    Adapter that posts image + text to a running OS-Atlas FastAPI service (the provider you showed).
    Expects the provider to be available at http://localhost:8000/predict by default.
    """

    integration_mode = IntegrationMode.PARTIAL
    capabilities = ["detect"]

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("OSATLAS_URL", "http://localhost:8000/predict")

    def _call_predict(self, image_path: str, text: str = "") -> Dict[str, Any]:
        url = self.base_url
        files = {}
        data = {"text": text}
        if image_path and os.path.exists(image_path):
            files["image"] = open(image_path, "rb")
        else:
            raise FileNotFoundError(f"Image not found at {image_path}")

        try:
            r = requests.post(url, files=files, data=data, timeout=30)
            r.raise_for_status()
            return r.json()
        finally:
            # close file handles
            if files:
                for f in files.values():
                    try:
                        f.close()
                    except Exception:
                        pass

    def detect(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        step should contain 'image_path' optionally, and 'text' describing the object to detect.
        Returns dict with keys like {"bbox": [x, y, w, h], "raw": {...}}
        """
        image_path = step.get("image_path")
        text = step.get("text", step.get("description", ""))

        resp = self._call_predict(image_path=image_path, text=text or "find target")
        # provider returns [x1,y1,x2,y2] in 'response'
        bbox_xyxy = resp.get("response", [])
        if not bbox_xyxy or len(bbox_xyxy) != 4:
            return {"bbox": None, "raw": resp}

        x1, y1, x2, y2 = bbox_xyxy
        # convert to x,y,w,h (w/h positive)
        x = int(x1)
        y = int(y1)
        w = int(x2) - x
        h = int(y2) - y
        w = max(1, w)
        h = max(1, h)
        return {"bbox": [x, y, w, h], "raw": resp}

    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        # Not an executor adapter — we only support detect here
        return {"status": "no-op", "reason": "osatlas adapter only supports detection via /predict"}

    def validate(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return {"validation": "unknown", "reason": "not implemented in OSAtlas adapter"}
