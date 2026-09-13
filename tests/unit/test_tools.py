import inspect
import pytest
from backend.tools.registry import ToolRegistry
from backend.tools.system_info import SystemInfoTool
from backend.tools.file_tools import (
    ListFilesTool,
    SearchFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateDirectoryTool,
    CopyFileTool,
    MoveFileTool,
)
from backend.tools.pc_tools import LaunchAppTool, OpenUrlTool, RunPCCommandTool


def test_tool_registration_and_execution():
    registry = ToolRegistry()
    tool = SystemInfoTool()
    
    registry.register(tool)
    assert registry.get_tool("get_system_info") is not None
    
    result = registry.execute_tool("get_system_info", {})
    assert "current_time" in result
    assert "operating_system" in result


def test_unregistered_tool_handling():
    registry = ToolRegistry()
    result = registry.execute_tool("non_existent_tool", {})
    assert "Error" in result


def test_file_tools_no_internal_guard_parameters():
    """Verify that no registered file tool exposes '_guard' or complex class types in parameter signatures."""
    registry = ToolRegistry()
    file_tools = [
        ListFilesTool(),
        SearchFilesTool(),
        ReadFileTool(),
        WriteFileTool(),
        CreateDirectoryTool(),
        CopyFileTool(),
        MoveFileTool(),
    ]
    for tool in file_tools:
        registry.register(tool)
        fn = tool.get_schema()
        sig = inspect.signature(fn)
        assert "_guard" not in sig.parameters, f"Tool {tool.name} exposes internal '_guard' in signature"
        
        # Verify OpenAI schema excludes _guard
        openai_schemas = registry.get_openai_schemas()
        for schema in openai_schemas:
            props = schema["function"]["parameters"]["properties"]
            assert "_guard" not in props, f"OpenAI schema for {schema['function']['name']} contains '_guard'"


def test_tool_alias_resolution(tmp_path):
    """Verify ToolRegistry resolves tools by internal name (files.list), sanitized name (files_list), or function name (list_files)."""
    from backend.security.path_guard import PathGuard
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])
    registry = ToolRegistry()
    tool = ListFilesTool(path_guard=guard)
    registry.register(tool)

    # Resolution checks
    assert registry.get_tool("files.list") is not None
    assert registry.get_tool("files_list") is not None
    assert registry.get_tool("list_files") is not None

    # Execution via all three names
    dir_path = str(tmp_path)
    res_internal = registry.execute_tool("files.list", {"directory_path": dir_path})
    res_sanitized = registry.execute_tool("files_list", {"directory_path": dir_path})
    res_fn = registry.execute_tool("list_files", {"directory_path": dir_path})

    assert "directory" in res_internal
    assert "directory" in res_sanitized
    assert "directory" in res_fn