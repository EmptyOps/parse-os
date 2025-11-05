import os
import sys
from pathlib import Path

# Add project root to sys.path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from os_automation.agents.executor_agent import ExecutorAgent
from os_automation.core.registry import registry
from os_automation.repos.mcp_adapter import MCPFileSystemAdapter

# def test_mcp_folder_creation(tmp_path):
#     """
#     ✅ Test direct MCP folder creation (no GUI involved)
#     """
#     adapter = MCPFileSystemAdapter()
#     base = tmp_path / "mcp_test"
#     adapter.base_path = str(base)
#     base.mkdir(exist_ok=True)

#     step = {"description": "create folder reports", "params": {"name": "reports"}}
#     result = adapter.execute(step)
#     print("Execute Result:", result)

#     target_path = base / "reports"
#     assert result["status"] == "success"
#     assert target_path.exists()
#     print(f"✅ Folder successfully created at: {target_path}")


# def test_mcp_file_creation(tmp_path):
#     """
#     ✅ Test direct MCP file creation (no GUI involved)
#     """
#     adapter = MCPFileSystemAdapter()
#     base = tmp_path / "mcp_test"
#     adapter.base_path = str(base)
#     base.mkdir(exist_ok=True)

#     step = {"description": "create file demo.txt", "params": {"name": "demo.txt", "content": "Hello MCP!"}}
#     result = adapter.execute(step)
#     print("Execute Result:", result)

#     target_path = base / "demo.txt"
#     assert result["status"] == "success"
#     assert target_path.exists()
#     print(f"✅ File successfully created at: {target_path}")
    
    
def test_mcp_write_and_read_file(tmp_path):
    """
    ✅ Test writing to a file and reading it back via MCP
    """
    adapter = MCPFileSystemAdapter()
    base = tmp_path / "mcp_test"
    base.mkdir(exist_ok=True)
    adapter.base_path = str(base)

    # Write content to file
    step_write = {"description": "create file notes.txt", "params": {"name": "notes.txt", "content": "Hello MCP Adapter!"}}
    result_write = adapter.execute(step_write)
    assert result_write["status"] == "success"

    # Read the content back
    file_path = base / "notes.txt"
    with open(file_path, "r") as f:
        content = f.read()

    assert content == "Hello MCP Adapter!"
    print(f"✅ File content verified: {content}")


def test_mcp_delete_folder(tmp_path):
    """
    ✅ Test folder deletion via MCP
    """
    adapter = MCPFileSystemAdapter()
    base = tmp_path / "mcp_test"
    base.mkdir(exist_ok=True)
    adapter.base_path = str(base)

    # Create folder first
    folder = base / "to_delete"
    folder.mkdir()
    assert folder.exists()

    # Delete folder step
    step_delete = {"description": "delete folder to_delete", "params": {"name": "to_delete"}}
    result_delete = adapter.execute(step_delete)
    print("Delete Result:", result_delete)

    # Check deletion
    assert not folder.exists()
    print(f"✅ Folder successfully deleted: {folder}")


def test_mcp_append_to_file(tmp_path):
    """
    ✅ Test appending content to an existing file
    """
    adapter = MCPFileSystemAdapter()
    base = tmp_path / "mcp_test"
    base.mkdir(exist_ok=True)
    adapter.base_path = str(base)

    file_path = base / "log.txt"
    file_path.write_text("Line 1\n")

    # Append new line via MCP
    step_append = {"description": "append to file log.txt", "params": {"name": "log.txt", "content": "Line 2\n", "mode": "a"}}
    result_append = adapter.execute(step_append)
    assert result_append["status"] == "success"

    # Verify
    content = file_path.read_text()
    assert content == "Line 1\nLine 2\n"
    print(f"✅ File append verified:\n{content}")



def test_executor_agent_with_mcp(tmp_path):
    # Prepare MCP adapter in tmp
    base = tmp_path / "mcp_test"
    base.mkdir(exist_ok=True)
    mcp = MCPFileSystemAdapter()
    mcp.base_path = str(base)
    
    # Register patched adapter
    registry.register_adapter("mcp_filesystem", lambda: mcp)

    agent = ExecutorAgent(default_executor="pyautogui")
    step = {"description": "create folder data", "params": {"name": "data"}}

    result = agent.execute_with_mcp_or_visual(step)
    print("MCP Execution Result:", result)
    assert result["status"] == "success"

    target_path = base / "data"
    assert target_path.exists()
    print(f"✅ ExecutorAgent successfully routed MCP and created {target_path}")


def test_mcp_validation_pass_and_fail(tmp_path):
    """
    ✅ Test MCP validation: should pass if target exists, fail if missing.
    """
    adapter = MCPFileSystemAdapter()
    base = tmp_path / "mcp_test"
    base.mkdir(exist_ok=True)
    adapter.base_path = str(base)

    # Create a file to validate existence
    file_path = base / "check.txt"
    file_path.write_text("data")

    # Validation should pass
    step_pass = {"description": "validate file", "params": {"name": "check.txt"}}
    val_pass = adapter.validate(step_pass)
    assert val_pass["validation_status"] == "pass"
    print(f"✅ Validation passed for existing file: {file_path}")

    # Validation should fail for missing file
    step_fail = {"description": "validate file", "params": {"name": "missing.txt"}}
    val_fail = adapter.validate(step_fail)
    assert val_fail["validation_status"] == "fail"
    print("✅ Validation failed for missing file as expected.")
