# os_automation/core/lifecycle.py

# from typing import Callable, Dict, List, Any


# class LifecycleManager:
#     def __init__(self):
#         self._registry: Dict[str, List[Callable]] = {}

#     def register(self, event_name: str, handler: Callable):
#         self._registry.setdefault(event_name, []).append(handler)

#     def emit(self, event_name: str, context: Dict[str, Any]):
#         handlers = self._registry.get(event_name, [])
#         for handler in handlers:
#             try:
#                 handler(context)
#             except Exception as e:
#                 print(f"[Lifecycle] Error in {event_name}: {e}")


# # Global instance (safe — no pro import here)
# lifecycle = LifecycleManager()


# os_automation/core/lifecycle.py
from typing import Callable, Dict, List, Any
from collections import defaultdict


class LifecycleManager:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

    def register(self, event: str, handler: Callable):
        self._handlers[event].append(handler)

    def emit(self, event: str, context: Dict[str, Any]) -> Dict[str, Any]:
        for handler in self._handlers.get(event, []):
            result = handler(context)
            if isinstance(result, dict):
                context.update(result)
        return context


# Singleton
lifecycle = LifecycleManager()