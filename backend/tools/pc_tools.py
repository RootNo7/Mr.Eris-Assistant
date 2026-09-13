import os
import subprocess
import webbrowser
import platform
from typing import Dict, Any, Callable
from backend.tools.base import BaseTool
from backend.security.enums import RiskLevel
from backend.core.logging.logger import logger


KNOWN_APP_MAP = {
    "notepad": "notepad.exe",
    "notepad.exe": "notepad.exe",
    "text editor": "notepad.exe",
    "calc": "calc.exe",
    "calc.exe": "calc.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "mspaint.exe": "mspaint.exe",
    "explorer": "explorer.exe",
    "explorer.exe": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "cmd.exe": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "powershell.exe": "powershell.exe",
    "terminal": "wt.exe",
    "wt.exe": "wt.exe",
    "code": "code",
    "vscode": "code",
    "browser": "msedge.exe",
    "edge": "msedge.exe",
    "msedge.exe": "msedge.exe",
    "chrome": "chrome.exe",
    "chrome.exe": "chrome.exe"
}


def launch_application(app_name: str) -> str:
    """Launches a desktop application on Windows (e.g. notepad, calc, mspaint, explorer, cmd, powershell, code).
    
    Args:
        app_name: The name or path of the application to launch (e.g., 'notepad', 'calc', 'chrome').
    """
    clean_name = app_name.strip().lower()
    if clean_name not in KNOWN_APP_MAP:
        logger.warning(f"Rejected launch of unknown application: '{app_name}'")
        return f"Error: Application '{app_name}' is not in the allowed application list."

    target_executable = KNOWN_APP_MAP[clean_name]

    try:
        logger.info(f"Launching application: '{target_executable}' (raw input: '{app_name}')")
        subprocess.Popen([target_executable], shell=False)
        return f"Successfully launched application: {app_name}"
    except Exception as e:
        logger.error(f"Failed to launch application '{app_name}': {e}")
        return f"Error launching application '{app_name}': {str(e)}"


class LaunchAppTool(BaseTool):
    name = "launch_application"
    description = "Launches a desktop application on Windows (e.g., notepad, calc, mspaint, explorer, cmd, powershell, code)."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "app.launch"
    required_permission = "process.manage"
    side_effect_level = "low"

    def execute(self, app_name: str = "notepad", **kwargs) -> str:
        return launch_application(app_name=app_name)

    def get_schema(self) -> Callable:
        return launch_application


def open_url(url: str) -> str:
    """Opens a web page URL or search query in the system default browser.
    
    Args:
        url: The web URL to open (e.g., 'https://google.com' or 'google.com').
    """
    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    try:
        logger.info(f"Opening URL in browser: {target_url}")
        webbrowser.open(target_url)
        return f"Successfully opened URL: {target_url}"
    except Exception as e:
        logger.error(f"Failed to open URL '{url}': {e}")
        return f"Error opening URL '{url}': {str(e)}"


class OpenUrlTool(BaseTool):
    name = "open_url"
    description = "Opens a web page URL in the user's default browser."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "browser.open"
    required_permission = "network.access"
    side_effect_level = "low"

    def execute(self, url: str = "", **kwargs) -> str:
        return open_url(url=url)

    def get_schema(self) -> Callable:
        return open_url


BLOCKED_COMMAND_KEYWORDS = [
    "format ",
    "rmdir /s",
    "del /f /s",
    "remove-item -recurse -force",
    "diskpart",
    "shutdown /s",
    "icacls",
    "mkfs"
]


def execute_pc_command(command: str) -> str:
    """Executes a shell command on the local Windows PC (PowerShell/CMD) and returns the console output.
    
    Args:
        command: The shell command line to execute.
    """
    cmd_lower = command.strip().lower()
    for keyword in BLOCKED_COMMAND_KEYWORDS:
        if keyword in cmd_lower:
            logger.warning(f"Blocked high-risk command execution attempt: '{command}'")
            return f"Error: Command blocked by ERIS security policy (contains high-risk pattern '{keyword}')."

    try:
        logger.info(f"Executing local PC command: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        output = (result.stdout + result.stderr).strip()
        return output if output else "Command executed successfully with no output."
    except subprocess.TimeoutExpired:
        logger.error(f"Command execution timed out: {command}")
        return f"Error: Command execution timed out after 15 seconds."
    except Exception as e:
        logger.error(f"Failed to execute command '{command}': {e}")
        return f"Error executing command '{command}': {str(e)}"


class RunPCCommandTool(BaseTool):
    name = "execute_pc_command"
    description = "Executes a safe shell command on the local Windows PC and returns the terminal output."
    risk_level = RiskLevel.T3
    requires_approval = True
    timeout_seconds = 15.0
    permission_scope = "terminal.execute"
    required_permission = "process.manage"
    side_effect_level = "high"

    def __init__(self):
        self._current_proc: Optional[subprocess.Popen] = None

    def execute(self, command: str = "", **kwargs) -> str:
        cmd_lower = command.strip().lower()
        for keyword in BLOCKED_COMMAND_KEYWORDS:
            if keyword in cmd_lower:
                logger.warning(f"Blocked high-risk command execution attempt: '{command}'")
                return f"Error: Command blocked by ERIS security policy (contains high-risk pattern '{keyword}')."

        try:
            logger.info(f"Executing local PC command: {command}")
            self._current_proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = self._current_proc.communicate(timeout=self.timeout_seconds)
            self._current_proc = None
            output = (stdout + stderr).strip()
            return output if output else "Command executed successfully with no output."
        except subprocess.TimeoutExpired:
            self.cancel()
            logger.error(f"Command execution timed out: {command}")
            return f"Error: Command execution timed out after {self.timeout_seconds} seconds."
        except Exception as e:
            self._current_proc = None
            logger.error(f"Failed to execute command '{command}': {e}")
            return f"Error executing command '{command}': {str(e)}"

    def cancel(self) -> None:
        if self._current_proc is not None:
            try:
                logger.warning(f"RunPCCommandTool: Killing process PID {self._current_proc.pid}")
                self._current_proc.kill()
            except Exception as e:
                logger.error(f"RunPCCommandTool cancel failed: {e}")
            finally:
                self._current_proc = None

    def get_schema(self) -> Callable:
        return execute_pc_command
