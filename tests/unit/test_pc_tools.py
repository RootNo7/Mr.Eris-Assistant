import pytest
from unittest.mock import patch, MagicMock
from backend.tools.pc_tools import (
    LaunchAppTool,
    OpenUrlTool,
    RunPCCommandTool,
    launch_application,
    open_url,
    execute_pc_command
)
from backend.tools.registry import ToolRegistry


@patch("backend.tools.pc_tools.subprocess.Popen")
def test_launch_application_success(mock_popen):
    mock_popen.return_value = MagicMock()
    result = launch_application("notepad")
    assert "Successfully launched application: notepad" in result
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


@patch("backend.tools.pc_tools.subprocess.Popen")
def test_launch_app_tool_execute(mock_popen):
    mock_popen.return_value = MagicMock()
    tool = LaunchAppTool()
    assert tool.name == "launch_application"
    result = tool.execute(app_name="calc")
    assert "Successfully launched application: calc" in result
    mock_popen.assert_called_once_with(["calc.exe"], shell=False)


@patch("backend.tools.pc_tools.subprocess.Popen")
def test_launch_application_unauthorized(mock_popen):
    result = launch_application("unauthorized_script.exe")
    assert "Error: Application 'unauthorized_script.exe' is not in the allowed application list." in result
    mock_popen.assert_not_called()


@patch("backend.tools.pc_tools.subprocess.Popen")
def test_launch_application_shell_injection(mock_popen):
    result = launch_application("notepad & calc")
    assert "Error: Application 'notepad & calc' is not in the allowed application list." in result
    mock_popen.assert_not_called()


@patch("backend.tools.pc_tools.webbrowser.open")
def test_open_url_success(mock_webbrowser_open):
    result = open_url("google.com")
    assert "Successfully opened URL: https://google.com" in result
    mock_webbrowser_open.assert_called_once_with("https://google.com")


@patch("backend.tools.pc_tools.webbrowser.open")
def test_open_url_tool_execute(mock_webbrowser_open):
    tool = OpenUrlTool()
    assert tool.name == "open_url"
    result = tool.execute(url="https://github.com")
    assert "Successfully opened URL: https://github.com" in result
    mock_webbrowser_open.assert_called_once_with("https://github.com")


@patch("backend.tools.pc_tools.subprocess.run")
def test_execute_pc_command_success(mock_run):
    mock_proc = MagicMock()
    mock_proc.stdout = "Windows IP Configuration"
    mock_proc.stderr = ""
    mock_run.return_value = mock_proc

    result = execute_pc_command("ipconfig")
    assert "Windows IP Configuration" in result
    mock_run.assert_called_once()


def test_execute_pc_command_blocked():
    result = execute_pc_command("rmdir /s /q C:\\Windows")
    assert "blocked by ERIS security policy" in result


def test_tool_registry_openai_schemas():
    registry = ToolRegistry()
    registry.register(LaunchAppTool())
    registry.register(OpenUrlTool())
    registry.register(RunPCCommandTool())

    schemas = registry.get_openai_schemas()
    assert len(schemas) == 3
    names = [s["function"]["name"] for s in schemas]
    assert "launch_application" in names
    assert "open_url" in names
    assert "execute_pc_command" in names
