import os
import shutil
import json
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from backend.tools.base import BaseTool
from backend.security.enums import RiskLevel
from backend.security.path_guard import PathGuard
from backend.core.exceptions import PathSecurityError, FileTooLargeError
from backend.core.logging.logger import logger


def _default_guard() -> PathGuard:
    """Create a default PathGuard using the project working directory."""
    return PathGuard()


# ---------------------------------------------------------------------------
# files.list
# ---------------------------------------------------------------------------

def list_files(directory_path: str = ".", **kwargs) -> str:
    """Lists files and directories within an allowed filesystem directory.
    
    Args:
        directory_path: Path to the directory to list (e.g. '.' or 'backend/storage').
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_dir = guard.validate_path(directory_path, check_exists=True)
        if not os.path.isdir(canonical_dir):
            return f"Error: Path '{directory_path}' is a file, not a directory."

        entries = []
        for entry in os.scandir(canonical_dir):
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return json.dumps({"directory": directory_path, "count": len(entries), "items": entries}, indent=2)

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except FileNotFoundError as fnf_err:
        return f"Error: {fnf_err}"
    except Exception as e:
        logger.error(f"Error in list_files: {e}")
        return f"Error listing directory '{directory_path}': {str(e)}"


class ListFilesTool(BaseTool):
    name = "files.list"
    description = "Lists files and subdirectories within an allowed filesystem directory."
    risk_level = RiskLevel.T0
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.read"
    required_permission = "filesystem.read"
    side_effect_level = "none"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, directory_path: str = ".", **kwargs) -> str:
        return list_files(directory_path=directory_path, _guard=self._guard)

    def get_schema(self) -> Callable:
        return list_files


# ---------------------------------------------------------------------------
# files.search
# ---------------------------------------------------------------------------

def search_files(query: str, directory_path: str = ".", extension: str = "", **kwargs) -> str:
    """Searches for files matching a query string inside an allowed directory tree.
    
    Args:
        query: Filename substring or search term.
        directory_path: Root directory to search from (e.g. '.').
        extension: Optional file extension filter (e.g. '.py' or '.json').
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_root = guard.validate_path(directory_path, check_exists=True)
        matches = []
        clean_ext = extension.strip().lower()
        clean_query = query.strip().lower()

        for root, _, files in os.walk(canonical_root):
            for file in files:
                if len(matches) >= 100:
                    break
                if clean_query in file.lower():
                    if clean_ext and not file.lower().endswith(clean_ext):
                        continue
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, canonical_root)
                    matches.append(rel_p)

        return json.dumps({"query": query, "count": len(matches), "matches": matches}, indent=2)

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except Exception as e:
        return f"Error searching files in '{directory_path}': {str(e)}"


class SearchFilesTool(BaseTool):
    name = "files.search"
    description = "Searches for matching filenames within an allowed directory tree."
    risk_level = RiskLevel.T0
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.read"
    required_permission = "filesystem.read"
    side_effect_level = "none"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, query: str = "", directory_path: str = ".", extension: str = "", **kwargs) -> str:
        return search_files(query=query, directory_path=directory_path,
                            extension=extension, _guard=self._guard)

    def get_schema(self) -> Callable:
        return search_files


# ---------------------------------------------------------------------------
# files.read
# ---------------------------------------------------------------------------

def read_file(file_path: str, **kwargs) -> str:
    """Reads and returns the text contents of a file within allowed filesystem boundaries.
    
    Args:
        file_path: Relative or absolute path to the target file.
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_file = guard.validate_path(file_path, check_exists=True)
        if os.path.isdir(canonical_file):
            return f"Error: Path '{file_path}' is a directory, not a file."

        file_size = os.path.getsize(canonical_file)
        guard.validate_file_size(file_size)

        with open(canonical_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except FileTooLargeError as size_err:
        return f"[SECURITY DENIAL] {size_err}"
    except FileNotFoundError as fnf_err:
        return f"Error: File not found: '{file_path}'"
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"


class ReadFileTool(BaseTool):
    name = "files.read"
    description = "Reads and returns the content of a text file within allowed filesystem boundaries."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.read"
    required_permission = "filesystem.read"
    side_effect_level = "none"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, file_path: str = "", **kwargs) -> str:
        return read_file(file_path=file_path, _guard=self._guard)

    def get_schema(self) -> Callable:
        return read_file


# ---------------------------------------------------------------------------
# files.write
# ---------------------------------------------------------------------------

def write_file(file_path: str, content: str, append: bool = False, **kwargs) -> str:
    """Writes text content to a file within allowed filesystem boundaries.
    
    Args:
        file_path: Target file path to write.
        content: The text string content to write.
        append: If True, appends content instead of overwriting.
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        guard.validate_file_size(len(content.encode("utf-8")))
        canonical_file = guard.validate_path(file_path, check_exists=False)

        parent_dir = os.path.dirname(canonical_file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        mode = "a" if append else "w"
        with open(canonical_file, mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended to" if append else "written to"
        return f"Successfully {action} file: {file_path} ({len(content)} characters)"

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except FileTooLargeError as size_err:
        return f"[SECURITY DENIAL] {size_err}"
    except Exception as e:
        return f"Error writing file '{file_path}': {str(e)}"


class WriteFileTool(BaseTool):
    name = "files.write"
    description = "Writes or appends text content to a file within allowed filesystem boundaries."
    risk_level = RiskLevel.T2
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.write"
    required_permission = "filesystem.write"
    side_effect_level = "medium"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, file_path: str = "", content: str = "", append: bool = False, **kwargs) -> str:
        return write_file(file_path=file_path, content=content, append=append, _guard=self._guard)

    def get_schema(self) -> Callable:
        return write_file


# ---------------------------------------------------------------------------
# files.create_directory
# ---------------------------------------------------------------------------

def create_directory(directory_path: str, **kwargs) -> str:
    """Creates a directory within allowed filesystem boundaries.
    
    Args:
        directory_path: Target directory path to create.
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_dir = guard.validate_path(directory_path, check_exists=False)
        os.makedirs(canonical_dir, exist_ok=True)
        return f"Successfully created directory: {directory_path}"

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except Exception as e:
        return f"Error creating directory '{directory_path}': {str(e)}"


class CreateDirectoryTool(BaseTool):
    name = "files.create_directory"
    description = "Creates a directory path within allowed filesystem boundaries."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 5.0
    permission_scope = "file.write"
    required_permission = "filesystem.write"
    side_effect_level = "low"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, directory_path: str = "", **kwargs) -> str:
        return create_directory(directory_path=directory_path, _guard=self._guard)

    def get_schema(self) -> Callable:
        return create_directory


# ---------------------------------------------------------------------------
# files.copy
# ---------------------------------------------------------------------------

def copy_file(source_path: str, destination_path: str, **kwargs) -> str:
    """Copies a file from source to destination within allowed filesystem boundaries.
    
    Args:
        source_path: Existing source file path.
        destination_path: Target destination file path.
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_src = guard.validate_path(source_path, check_exists=True)
        canonical_dst = guard.validate_path(destination_path, check_exists=False)

        guard.validate_file_size(os.path.getsize(canonical_src))

        parent_dir = os.path.dirname(canonical_dst)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        shutil.copy2(canonical_src, canonical_dst)
        return f"Successfully copied '{source_path}' to '{destination_path}'"

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except FileTooLargeError as size_err:
        return f"[SECURITY DENIAL] {size_err}"
    except FileNotFoundError:
        return f"Error: File not found: '{source_path}'"
    except Exception as e:
        return f"Error copying '{source_path}' to '{destination_path}': {str(e)}"


class CopyFileTool(BaseTool):
    name = "files.copy"
    description = "Copies a file within allowed filesystem boundaries."
    risk_level = RiskLevel.T2
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.write"
    required_permission = "filesystem.write"
    side_effect_level = "medium"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, source_path: str = "", destination_path: str = "", **kwargs) -> str:
        return copy_file(source_path=source_path, destination_path=destination_path, _guard=self._guard)

    def get_schema(self) -> Callable:
        return copy_file


# ---------------------------------------------------------------------------
# files.move
# ---------------------------------------------------------------------------

def move_file(source_path: str, destination_path: str, **kwargs) -> str:
    """Moves or renames a file/directory from source to destination within allowed filesystem boundaries.
    
    Args:
        source_path: Existing source file/dir path.
        destination_path: Target destination path.
    """
    guard = kwargs.get("_guard") or _default_guard()
    try:
        canonical_src = guard.validate_path(source_path, check_exists=True)
        canonical_dst = guard.validate_path(destination_path, check_exists=False)

        parent_dir = os.path.dirname(canonical_dst)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        shutil.move(canonical_src, canonical_dst)
        return f"Successfully moved '{source_path}' to '{destination_path}'"

    except PathSecurityError as sec_err:
        return f"[SECURITY DENIAL] {sec_err}"
    except FileNotFoundError:
        return f"Error: File not found: '{source_path}'"
    except Exception as e:
        return f"Error moving '{source_path}' to '{destination_path}': {str(e)}"


class MoveFileTool(BaseTool):
    name = "files.move"
    description = "Moves or renames a file or directory within allowed filesystem boundaries."
    risk_level = RiskLevel.T2
    requires_approval = False
    timeout_seconds = 10.0
    permission_scope = "file.write"
    required_permission = "filesystem.write"
    side_effect_level = "medium"

    def __init__(self, path_guard: Optional[PathGuard] = None):
        self._guard = path_guard

    def execute(self, source_path: str = "", destination_path: str = "", **kwargs) -> str:
        return move_file(source_path=source_path, destination_path=destination_path, _guard=self._guard)

    def get_schema(self) -> Callable:
        return move_file
