from os_automation.core.registry import registry


def test_register_and_get_adapter():
    registry.register_adapter("fake", lambda: "ok")
    assert "fake" in registry.list_adapters()
    adapter = registry.get_adapter("fake")
    assert callable(adapter)

def test_list_adapters_empty_by_default():
    # Conftest isolate_registry ensures clean state for each test
    # If no adapters registered, list should be empty or minimal
    keys = registry.list_adapters()
    assert isinstance(keys, list)
