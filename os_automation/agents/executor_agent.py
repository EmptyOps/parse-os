# os_automation/agents/executor_agent.py
from typing import Any, Dict, Optional

from os_automation.core.registry import registry
from os_automation.core.tal import ExecutionResult


class ExecutorAgent:
    """
    Unified agent: performs detection (via detection adapter) and execution (via executor adapter).
    Business logic from your original scripts is preserved by calling their ToolWrapper classes.
    
    🧩 Extended: Adds MCP-first routing.
    If a Modular Capability Provider (e.g., MCPFileSystemAdapter) is available
    and capable of handling the current step, it executes it directly
    without falling back to GUI tools like PyAutoGUI or Sikuli.
    """

    def __init__(self, default_detection: str = "omniparser", default_executor: str = "pyautogui"):
        self.default_detection = default_detection
        self.default_executor = default_executor

    # ----------------------------------------------------------------------------------------
    # ORIGINAL METHODS (kept intact)
    # ----------------------------------------------------------------------------------------

    def _get_detection_adapter(self, name: Optional[str] = None):
        n = name or self.default_detection
        adapter_factory = registry.get_adapter(n)
        if adapter_factory is None:
            raise RuntimeError(f"Detection adapter '{n}' not registered")
        return adapter_factory() if callable(adapter_factory) else adapter_factory

    def _get_executor_adapter(self, name: Optional[str] = None):
        n = name or self.default_executor
        adapter_factory = registry.get_adapter(n)
        if adapter_factory is None:
            raise RuntimeError(f"Executor adapter '{n}' not registered")
        return adapter_factory() if callable(adapter_factory) else adapter_factory

    def detect(self, image_path: str, detection_name: Optional[str] = None) -> Dict[str, Any]:
        adapter = self._get_detection_adapter(detection_name)
        # adapter.detect expects a step-like dict ({"image_path": ...})
        return adapter.detect({"image_path": image_path})

    def execute(self, bbox: list, event: str, executor_name: Optional[str] = None,
                text: Optional[str] = None) -> Dict[str, Any]:
        adapter = self._get_executor_adapter(executor_name)
        # We pass same shape step payload expected by executor adapters
        step_payload = {"bbox": bbox, "event": event, "text": text}
        return adapter.execute(step_payload)

    def detect_and_execute(self, image_path: str, decide_func=None,
                           executor_name: Optional[str] = None,
                           detection_name: Optional[str] = None):
        """
        Convenience: detect -> choose bbox -> decide event using decide_func(planned_step) -> execute
        decide_func(planned_step) should return ("click"|"type"|"scroll", optional_text)
        """
        detections = self.detect(image_path, detection_name=detection_name)
        # collect bboxes from detection output
        bboxes = []
        for v in detections.values():
            if isinstance(v, dict) and "bbox" in v:
                bboxes.append(v["bbox"])
        chosen = bboxes[0] if bboxes else [10, 10, 50, 50]
        # if no decision function provided default to click
        if decide_func:
            event, text = decide_func()
        else:
            event, text = ("click", None)
        exec_out = self.execute(chosen, event, executor_name=executor_name, text=text)
        return {
            "detection": detections,
            "chosen_bbox": chosen,
            "execution": exec_out
        }

    # ----------------------------------------------------------------------------------------
    # NEW MCP-AWARE EXTENSION (safe and optional)
    # ----------------------------------------------------------------------------------------

    def execute_with_mcp_or_visual(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extended capability routing:
        Try executing via MCP (Modular Capability Provider) first,
        and if not available or not successful, fall back to normal visual execution.

        Example:
            step = {
                "description": "Create folder named reports",
                "params": {"name": "reports"}
            }
        """

        # 1️⃣ Try MCP adapter if available
        mcp_adapter_cls = registry.get_adapter("mcp_filesystem")
        if mcp_adapter_cls:
            mcp_adapter = mcp_adapter_cls()
            try:
                mcp_result = mcp_adapter.execute(step)
                if mcp_result.get("status") == "success":
                    print("[MCP] Executed via MCPFileSystemAdapter")
                    return mcp_result
            except Exception as e:
                print(f"[MCP] Failed or unsupported: {e}")

        # 2️⃣ Fallback to visual automation
        print("[Fallback] Using visual executor")
        bbox = step.get("bbox", [10, 10, 100, 40])
        event = step.get("event", "click")
        text = step.get("text")

        exec_adapter = self._get_executor_adapter(self.default_executor)
        return exec_adapter.execute({"bbox": bbox, "event": event, "text": text})
