# os_automation/validators/bbox_validator.py
class BoundingBoxValidator:
    def validate(self, step, execution_result):
        details = execution_result.get("details", {}) if isinstance(execution_result, dict) else {}
        detection = details.get("detection") if isinstance(details, dict) else None
        bboxes = []
        if detection:
            for v in detection.values():
                if isinstance(v, dict) and "bbox" in v:
                    bboxes.append(v["bbox"])
        if not bboxes:
            return {"validation_status": "fail", "reason": "no bounding boxes found"}
        first = bboxes[0]
        label = (first.get("label") or "").lower() if isinstance(first, dict) else ""
        text = (first.get("text") or "").lower() if isinstance(first, dict) else ""
        desc = (step.get("description") or "").lower() if isinstance(step, dict) else ""
        if label and label in desc:
            return {"validation_status": "pass", "reason": "label matches description", "bbox": first}
        if text and text in desc:
            return {"validation_status": "pass", "reason": "text matches description", "bbox": first}
        return {"validation_status": "pass", "reason": "bbox found (fuzzy)", "bbox": first}
