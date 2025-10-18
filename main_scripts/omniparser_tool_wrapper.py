# main_scripts/omniparser_tool_wrapper.py
import os
import sys
from pathlib import Path
from PIL import Image
import torch

# Allow using OMNIPARSER_ROOT env var or configs->project_root
OMNI_ROOT = os.environ.get("OMNIPARSER_ROOT", "").strip()
if OMNI_ROOT:
    sys.path.insert(0, OMNI_ROOT)

# If you have the real OmniParser repo available, you can import its utils here.
# For safety this wrapper preserves your original logic pattern and is testable.
try:
    # Attempt to import real functions if absolute path present
    # from util.utils import check_ocr_box, get_yolo_model, get_caption_model_processor, get_som_labeled_img
    HAS_REAL = False
except Exception:
    HAS_REAL = False

class ToolWrapper:
    def __init__(self):
        self.device = torch.device("cpu")
        # load models if you want when OMNI is available - keep your logic unchanged here

    def _rescale_bbox(self, bbox, img_width, img_height):
        x1, y1, x2, y2 = bbox
        x = int(x1 * img_width)
        y = int(y1 * img_height)
        w = int((x2 - x1) * img_width)
        h = int((y2 - y1) * img_height)
        return [x, y, w, h]

    def process_image(self, image_path, box_threshold=0.05, iou_threshold=0.1, use_paddleocr=True, imgsz=640):
        """
        Your original logic goes here. This scaffold returns a demo detection.
        Replace with your full implementation (weights, model loading) anytime.
        """
        image = Image.open(image_path).convert("RGB")
        w, h = image.size
        fake_rel = [0.1, 0.1, 0.25, 0.2]
        abs_bbox = self._rescale_bbox(fake_rel, w, h)
        results = {
            "ocr_text_combined": "demo text",
            "icon_0": {"type": "icon", "bbox": abs_bbox, "content": "demo_icon"},
            "text_0": {"type": "text", "bbox": abs_bbox, "content": "demo_text"}
        }
        return results
