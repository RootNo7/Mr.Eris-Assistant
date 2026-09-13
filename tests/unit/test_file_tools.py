import os
import json
import pytest
from backend.security.path_guard import PathGuard
from backend.core.exceptions import PathTraversalError, UnauthorizedPathError, FileTooLargeError
from backend.tools.file_tools import (
    ListFilesTool,
    SearchFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateDirectoryTool,
    CopyFileTool,
    MoveFileTool
)
from backend.tools.registry import ToolRegistry


@pytest.fixture
def scoped_guard(tmp_path):
    """Creates a PathGuard scoped to tmp_path as the sole allowed root."""
    return PathGuard(allowed_roots=[str(tmp_path.resolve())], max_file_size=1_000_000)


@pytest.fixture
def scoped_registry(scoped_guard):
    """Creates a ToolRegistry populated with all file tools scoped to tmp_path."""
    from backend.security.executor import CentralToolExecutor
    from backend.security.approval import AutoApprovalGate
    executor = CentralToolExecutor(approval_gate=AutoApprovalGate(default_approved=True))
    registry = ToolRegistry(executor=executor)
    registry.register(ListFilesTool(path_guard=scoped_guard))
    registry.register(SearchFilesTool(path_guard=scoped_guard))
    registry.register(ReadFileTool(path_guard=scoped_guard))
    registry.register(WriteFileTool(path_guard=scoped_guard))
    registry.register(CreateDirectoryTool(path_guard=scoped_guard))
    registry.register(CopyFileTool(path_guard=scoped_guard))
    registry.register(MoveFileTool(path_guard=scoped_guard))
    return registry


# ---------------------------------------------------------------------------
# PathGuard Unit Tests (direct)
# ---------------------------------------------------------------------------

def test_path_guard_valid_path(tmp_path):
    """Valid subpath within allowed root resolves correctly."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])
    valid_file = tmp_path / "test.txt"
    valid_file.write_text("hello")

    resolved = guard.validate_path(str(valid_file))
    assert resolved == os.path.realpath(str(valid_file))


def test_path_guard_invalid_path(tmp_path):
    """Path completely outside allowed roots raises UnauthorizedPathError."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])
    with pytest.raises(UnauthorizedPathError):
        guard.validate_path("C:\\Windows\\System32\\cmd.exe")


def test_path_traversal_attempt(tmp_path):
    """Explicit ../ traversal that would escape allowed root raises PathTraversalError."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])

    # Construct a traversal path that starts from within tmp_path but escapes it
    nested = tmp_path / "sub"
    nested.mkdir()
    traversal = str(nested / ".." / ".." / ".." / "Windows" / "System32")
    with pytest.raises((PathTraversalError, UnauthorizedPathError)):
        guard.validate_path(traversal)


def test_symlink_escape(tmp_path):
    """Symlink inside allowed root pointing outside it raises PathTraversalError."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])

    outside_dir = tmp_path.parent / "outside_secret_target"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "target.txt"
    outside_file.write_text("secret_data")

    symlink_path = tmp_path / "escapelink.txt"
    try:
        os.symlink(str(outside_file), str(symlink_path))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated privileges on this OS.")

    with pytest.raises(PathTraversalError):
        guard.validate_path(str(symlink_path))


def test_large_file_rejection(tmp_path):
    """File size exceeding limit raises FileTooLargeError."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())], max_file_size=100)
    with pytest.raises(FileTooLargeError):
        guard.validate_file_size(200)


# ---------------------------------------------------------------------------
# Tool Integration Tests (via Registry)
# ---------------------------------------------------------------------------

def test_normal_write_and_read(tmp_path, scoped_registry):
    """Write then read a file within the allowed tmp_path root."""
    write_res = scoped_registry.execute_tool("files.write", {
        "file_path": str(tmp_path / "hello.txt"),
        "content": "Hello ERIS Filesystem!"
    })
    assert "Successfully written to file" in write_res

    read_res = scoped_registry.execute_tool("files.read", {
        "file_path": str(tmp_path / "hello.txt")
    })
    assert read_res == "Hello ERIS Filesystem!"


def test_create_directory(tmp_path, scoped_registry):
    """Create a subdirectory within the allowed root."""
    target_dir = str(tmp_path / "my_subdir")
    mkdir_res = scoped_registry.execute_tool("files.create_directory", {"directory_path": target_dir})
    assert "Successfully created directory" in mkdir_res
    assert os.path.isdir(target_dir)


def test_list_and_search_files(tmp_path, scoped_registry):
    """List and search files created within the tmp_path root."""
    (tmp_path / "doc1.txt").write_text("test 1")
    (tmp_path / "doc2.json").write_text("{}")

    list_res = scoped_registry.execute_tool("files.list", {"directory_path": str(tmp_path)})
    assert "doc1.txt" in list_res
    assert "doc2.json" in list_res

    search_res = scoped_registry.execute_tool("files.search", {
        "query": "doc",
        "directory_path": str(tmp_path),
        "extension": ".json"
    })
    assert "doc2.json" in search_res
    assert "doc1.txt" not in search_res


def test_copy_and_move_files(tmp_path, scoped_registry):
    """Copy and move files within the allowed tmp_path root."""
    src = tmp_path / "original.txt"
    src.write_text("sample")
    dst_copy = str(tmp_path / "copied.txt")
    dst_move = str(tmp_path / "moved.txt")

    copy_res = scoped_registry.execute_tool("files.copy", {
        "source_path": str(src),
        "destination_path": dst_copy
    })
    assert "Successfully copied" in copy_res
    assert os.path.exists(dst_copy)

    move_res = scoped_registry.execute_tool("files.move", {
        "source_path": dst_copy,
        "destination_path": dst_move
    })
    assert "Successfully moved" in move_res
    assert os.path.exists(dst_move)
    assert not os.path.exists(dst_copy)


def test_nonexistent_file_error(tmp_path, scoped_registry):
    """Reading a nonexistent file returns a clear error message."""
    res = scoped_registry.execute_tool("files.read", {
        "file_path": str(tmp_path / "ghost_file.txt")
    })
    assert "Error:" in res or "not found" in res.lower()


def test_unauthorized_root_denial(tmp_path):
    """Tool scoped to tmp_path rejects paths outside that root."""
    guard = PathGuard(allowed_roots=[str(tmp_path.resolve())])
    registry = ToolRegistry()
    registry.register(ReadFileTool(path_guard=guard))

    res = registry.execute_tool("files.read", {"file_path": "C:\\Windows\\System32\\drivers\\etc\\hosts"})
    assert "[SECURITY DENIAL]" in res
