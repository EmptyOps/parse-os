import pytest
from PIL import Image
from pathlib import Path
from os_automation.core.registry import registry

@pytest.fixture(autouse=True)
def isolate_registry():
    """
    Save & restore registry adapters/agents around each test to avoid cross-test leakage.
    """
    # These attributes exist in the registry implementation we used earlier.
    saved_adapters = dict(getattr(registry, "_adapters", {}))
    saved_agents = dict(getattr(registry, "_agents", {})) if hasattr(registry, "_agents") else {}
    try:
        yield
    finally:
        # restore adapters
        if hasattr(registry, "_adapters"):
            registry._adapters.clear()
            registry._adapters.update(saved_adapters)
        # restore agents
        if hasattr(registry, "_agents"):
            registry._agents.clear()
            registry._agents.update(saved_agents)

@pytest.fixture
def tmp_image(tmp_path: Path):
    """
    Create a small plain PNG to use for detection adapters that open images.
    """
    img_path = tmp_path / "sample.png"
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img.save(img_path)
    return str(img_path)
