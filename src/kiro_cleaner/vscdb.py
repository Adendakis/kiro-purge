"""Read-only accessor for Kiro workspace state databases (``state.vscdb``).

Kiro stores per-workspace workbench and agent-session metadata in a SQLite
database at ``User/workspaceStorage/<workspace-hash>/state.vscdb`` with a single
``ItemTable(key, value)``. This module reads that database strictly read-only
(``mode=ro``) for the purpose of attributing storage to a project folder and
never modifies it. Any error (locked, corrupt, missing) is swallowed so callers
can fall back to other attribution sources.
"""

import json
import re
import sqlite3
import urllib.parse
from pathlib import Path

# Matches a file:// folder reference, capturing the (possibly URL-encoded) path.
_FILE_URI_RE = re.compile(r"file://(/[^\"\\?#]+)")


def read_item(db_path: Path, key: str) -> str | None:
    """Return the value for ``key`` in the ItemTable, or ``None``.

    Opens the database read-only. Returns ``None`` on any error (missing file,
    locked or corrupt database, missing table/key) rather than raising, so the
    caller can fall back to another attribution source.
    """
    if not db_path.is_file():
        return None
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None
    except (sqlite3.Error, OSError):
        return None
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass


def _decode_file_uri(uri_path: str) -> str:
    """URL-decode a captured file:// path (e.g. ``MXP%20Agent`` -> ``MXP Agent``)."""
    return urllib.parse.unquote(uri_path)


def folder_from_workspace_json(workspace_dir: Path) -> str | None:
    """Read the project folder from ``workspace.json`` if present.

    The file looks like ``{"folder": "file:///Users/.../Project"}``.
    Returns the decoded filesystem path, or ``None``.
    """
    wj = workspace_dir / "workspace.json"
    if not wj.is_file():
        return None
    try:
        data = json.loads(wj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    folder = data.get("folder") if isinstance(data, dict) else None
    if not isinstance(folder, str):
        return None
    m = _FILE_URI_RE.search(folder)
    if m:
        return _decode_file_uri(m.group(1))
    return None


def _coarse_root(decoded_path: str) -> str | None:
    """Reduce a decoded file path to a coarse ``/<a>/<user>/<project>`` root."""
    parts = [p for p in decoded_path.split("/") if p]
    if len(parts) < 3:
        return None
    return "/" + "/".join(parts[:3])


def folder_from_state_db(workspace_dir: Path) -> str | None:
    """Best-effort project folder from a ``file://`` reference in ``state.vscdb``.

    Reads the ``history.entries`` and ``kiro.kiroAgent`` values (read-only) and
    returns the most common ``/Users/<user>/<project>`` style root among any
    ``file://`` references found, ignoring Kiro's own storage directory. The
    references point at individual files, so each is reduced to its coarse
    project root before tallying.
    """
    db = workspace_dir / "state.vscdb"
    counts: dict[str, int] = {}
    for key in ("history.entries", "kiro.kiroAgent"):
        value = read_item(db, key)
        if not value:
            continue
        for uri_path in _FILE_URI_RE.findall(value):
            decoded = _decode_file_uri(uri_path)
            if "Application Support" in decoded or "/globalStorage/" in decoded:
                continue
            root = _coarse_root(decoded)
            if root is None:
                continue
            counts[root] = counts.get(root, 0) + 1
    if not counts:
        return None
    # Return the most frequently referenced root.
    return max(counts, key=lambda k: counts[k])


def workspace_folder(workspace_dir: Path) -> str | None:
    """Resolve a ``workspaceStorage/<hash>`` dir to its project folder path.

    Prefers ``workspace.json`` (authoritative), then falls back to a ``file://``
    reference inside ``state.vscdb``. Returns ``None`` if neither resolves.
    """
    return folder_from_workspace_json(workspace_dir) or folder_from_state_db(
        workspace_dir
    )
