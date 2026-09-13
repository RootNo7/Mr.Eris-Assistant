import os
from pathlib import Path
from typing import List, Optional
from backend.core.exceptions import PathTraversalError, UnauthorizedPathError, FileTooLargeError
from backend.core.logging.logger import logger
from backend.core.config.settings import Config


class PathGuard:
    """
    Filesystem Security Guard enforcing canonicalization, allowed root boundaries,
    traversal prevention, symlink escape protection, and file size limits.
    """

    def __init__(self, allowed_roots: Optional[List[str]] = None, max_file_size: Optional[int] = None, config: Optional[Config] = None):
        self.config = config or Config()
        
        # 1. Resolve and canonicalize allowed root directories
        if allowed_roots:
            raw_roots = allowed_roots
        else:
            configured_roots = getattr(self.config, "ERIS_ALLOWED_FS_ROOTS", None)
            if configured_roots:
                if isinstance(configured_roots, str):
                    raw_roots = [r.strip() for r in configured_roots.split(";") if r.strip()]
                else:
                    raw_roots = configured_roots
            else:
                raw_roots = [os.getcwd()]

        self.allowed_roots: List[str] = []
        for root in raw_roots:
            real_root = os.path.realpath(os.path.abspath(root))
            if real_root not in self.allowed_roots:
                self.allowed_roots.append(real_root)

        # 2. File size limit (default 10MB)
        if max_file_size is not None:
            self.max_file_size = max_file_size
        else:
            self.max_file_size = getattr(self.config, "ERIS_MAX_FILE_SIZE_BYTES", 10485760)

    def is_within_root(self, target_path: str, root_path: str) -> bool:
        """Helper checking if target_path is equal to or inside root_path."""
        try:
            target_p = Path(target_path).resolve()
            root_p = Path(root_path).resolve()
            return target_p == root_p or root_p in target_p.parents
        except Exception:
            return False

    def validate_path(self, path_input: str, check_exists: bool = False) -> str:
        """
        Validates, canonicalizes, and verifies that path_input resides strictly inside allowed roots.
        Raises PathTraversalError, UnauthorizedPathError, or FileNotFoundError.
        Returns the resolved canonical path string.
        """
        if not path_input or not path_input.strip():
            raise UnauthorizedPathError("Path input cannot be empty.")

        # Canonicalize target path (resolves symlinks, relative components . and ..)
        try:
            abs_path = os.path.abspath(path_input.strip())
            canonical_path = os.path.realpath(abs_path)
        except Exception as e:
            raise PathTraversalError(f"Invalid path format '{path_input}': {e}") from e

        # Boundary Check against allowed roots
        is_authorized = False
        for root in self.allowed_roots:
            if self.is_within_root(canonical_path, root):
                is_authorized = True
                break

        if not is_authorized:
            logger.warning(f"PathGuard BLOCKED: '{path_input}' (canonical: '{canonical_path}') outside allowed roots {self.allowed_roots}")
            # Differentiate explicit relative traversal attempt vs out-of-root path
            if ".." in path_input or ".." in abs_path:
                raise PathTraversalError(f"Access denied: Path traversal attempt detected in '{path_input}'.")
            raise UnauthorizedPathError(f"Access denied: Path '{path_input}' is outside allowed filesystem roots.")

        # Symlink Escape Check
        if os.path.islink(path_input):
            symlink_target = os.path.realpath(path_input)
            symlink_authorized = any(self.is_within_root(symlink_target, root) for root in self.allowed_roots)
            if not symlink_authorized:
                logger.warning(f"PathGuard BLOCKED Symlink Escape: '{path_input}' points to '{symlink_target}'")
                raise PathTraversalError(f"Access denied: Symlink '{path_input}' points outside allowed filesystem roots.")

        # Existence Check
        if check_exists and not os.path.exists(canonical_path):
            raise FileNotFoundError(f"File or directory not found: '{path_input}'")

        return canonical_path

    def validate_file_size(self, size_bytes: int) -> None:
        """Enforces maximum allowed file size limit."""
        if size_bytes > self.max_file_size:
            raise FileTooLargeError(
                f"File size ({size_bytes} bytes) exceeds maximum allowed limit ({self.max_file_size} bytes)."
            )
