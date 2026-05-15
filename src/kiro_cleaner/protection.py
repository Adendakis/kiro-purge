"""Protection guard for critical Kiro configuration files and directories."""

from pathlib import Path

PROTECTED_FILES: set[str] = {
    "config.json",
    "settings.json",
    "mcp.json",
    "sessions.json",
    "state.vscdb",
    "workspace.json",
    "storage.json",
}

PROTECTED_DIRECTORIES: set[str] = {"index", ".migrations", "lancedb"}


def is_protected(path: Path) -> tuple[bool, str | None]:
    """Check if a path is protected.

    A path is protected if:
    - Its filename matches any entry in PROTECTED_FILES
    - Any component of the path matches a PROTECTED_DIRECTORIES entry

    Args:
        path: The file path to check.

    Returns:
        A tuple of (is_protected, reason). If protected, reason describes why.
        If not protected, reason is None.
    """
    # Check if the filename matches a protected file
    if path.name in PROTECTED_FILES:
        return (True, f"Protected file: {path.name}")

    # Check if any path component matches a protected directory
    for part in path.parts:
        if part in PROTECTED_DIRECTORIES:
            return (True, f"Protected directory: {part}")

    return (False, None)
