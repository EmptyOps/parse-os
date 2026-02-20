# os_automation/core/lifecycle.py

from typing import Callable, Dict, List, Any


class LifecycleManager:
    def __init__(self):
        self._registry: Dict[str, List[Callable]] = {}

    def register(self, event_name: str, handler: Callable):
        self._registry.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, context: Dict[str, Any]):
        handlers = self._registry.get(event_name, [])
        for handler in handlers:
            try:
                handler(context)
            except Exception as e:
                print(f"[Lifecycle] Error in {event_name}: {e}")


# Global instance (safe — no pro import here)
lifecycle = LifecycleManager()