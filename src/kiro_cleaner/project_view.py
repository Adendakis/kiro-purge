"""Project-aggregated view over a completed scan.

Groups scanned Kiro storage by the project folder it belongs to, rather than by
Category. This is a read-only report: it consumes the absolute paths already
collected by :func:`kiro_cleaner.scanner.scan_storage` and attributes each
kiroagent workspace-hash directory to a project folder.

Attribution (Requirement 13.2), best-effort per hash directory, in order:
  1. a project folder from ``known_roots`` (workspaceStorage) that is a prefix
     of a referenced path
  2. the ``documentUri`` field of any ``.json`` metadata file in the hash dir
  3. a ``file://`` reference embedded in that hash dir's extension-less Session_Logs

Files not under any workspace-hash dir (logs, cache, history, crash reports, and
the top-level shared ``index/``) are Kiro-framework-level and reported under the
"(global)" group. A hash dir with no recoverable project goes under the
"(unknown-project)" group. Together with resolved projects this yields a
total-preserving partition of the scan (Property 17).

Note: the ``globalStorage/kiro.kiroagent/<hash>`` namespace and the
``workspaceStorage/<hash>`` namespace use *different* hashes and do not
cross-reference, so attribution relies on the folder paths recorded inside the
hash dir's own files.
"""

import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from kiro_cleaner.scanner import ScanResult

_KIROAGENT_PREFIX = "User/globalStorage/kiro.kiroagent"

# Distinct group labels for data that is not a resolved project folder.
GLOBAL_GROUP = "(global)"                     # framework-level: logs/cache/history/index
UNKNOWN_PROJECT_GROUP = "(unknown-project)"   # kiroagent hash with no recoverable path

# A /Users/<user>/<project> style root captured from a file:// reference.
_FILE_URI_RE = re.compile(r"file://(/[^\"\\?#]+)")


@dataclass
class ProjectGroup:
    """Aggregated storage for a single project folder."""

    project: str
    total_bytes: int = 0
    category_bytes: dict[str, int] = field(default_factory=dict)
    newest_mtime: float | None = None
    workspace_hashes: list[str] = field(default_factory=list)


@dataclass
class ProjectView:
    """A read-only report grouping storage by project folder."""

    groups: list[ProjectGroup]
    total_bytes: int


def _decode(uri_path: str) -> str:
    return urllib.parse.unquote(uri_path)


def _project_root_fallback(decoded_path: str) -> str | None:
    """Reduce a decoded file:// path to a coarse project root.

    Used only when the path does not sit under a known workspace folder. Kiro
    records references to individual files deep inside a project; as a last
    resort we take the first three path components below root (e.g.
    ``/Users/alice/myproject``). Returns ``None`` for paths too shallow.
    """
    parts = [p for p in decoded_path.split("/") if p]
    if len(parts) < 3:
        return None
    return "/" + "/".join(parts[:3])


def known_project_roots(kiro_storage: Path) -> list[str]:
    """Collect authoritative project folders from workspaceStorage.

    Reads every ``workspaceStorage/<hash>/`` folder reference (workspace.json,
    then state.vscdb) read-only. These are the exact project folders Kiro opened,
    so they let us attribute a file reference to the right project regardless of
    nesting depth. Returned longest-first for greedy longest-prefix matching.
    """
    # Local import to avoid a hard dependency cycle at module import time.
    from kiro_cleaner.vscdb import workspace_folder

    roots: set[str] = set()
    ws_root = kiro_storage / "User" / "workspaceStorage"
    if ws_root.is_dir():
        for entry in ws_root.iterdir():
            if not entry.is_dir():
                continue
            folder = workspace_folder(entry)
            if folder:
                roots.add(folder.rstrip("/"))
    return sorted(roots, key=len, reverse=True)


def _match_known_root(decoded_path: str, known_roots: list[str]) -> str | None:
    """Return the longest known project root that is a prefix of ``decoded_path``."""
    for root in known_roots:  # already sorted longest-first
        if decoded_path == root or decoded_path.startswith(root + "/"):
            return root
    return None


def _project_from_text(text: str, known_roots: list[str]) -> str | None:
    """Return the most common project root among file:// refs in ``text``.

    Prefers matching against a known workspace folder (authoritative, depth-aware);
    otherwise falls back to a coarse 3-segment root.
    """
    counts: dict[str, int] = {}
    for uri_path in _FILE_URI_RE.findall(text):
        decoded = _decode(uri_path)
        if "Application Support" in decoded or "/globalStorage/" in decoded:
            continue
        root = _match_known_root(decoded, known_roots) or _project_root_fallback(decoded)
        if root is None:
            continue
        counts[root] = counts.get(root, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def _project_from_json_document_uris(hash_dir: Path, known_roots: list[str]) -> str | None:
    """Resolve a project from ``documentUri`` fields in ``.json`` files.

    Kiro writes spec/metadata ``.json`` files (e.g. requirements.md snapshots)
    carrying a ``documentUri`` like ``file:///Users/you/project/.kiro/...``.
    These reliably name the owning project even when the bulk Session_Logs are
    path-free. Returns the most common resolved project root, or ``None``.
    """
    counts: dict[str, int] = {}
    scanned = 0
    for dp, dirnames, filenames in os.walk(hash_dir):
        dirnames[:] = [d for d in dirnames if d != "index"]
        for name in filenames:
            if not name.endswith(".json"):
                continue
            scanned += 1
            if scanned > 4000:
                break
            p = Path(dp) / name
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            uri = data.get("documentUri")
            if not isinstance(uri, str):
                continue
            m = _FILE_URI_RE.search(uri)
            if not m:
                continue
            decoded = _decode(m.group(1))
            if "Application Support" in decoded or "/globalStorage/" in decoded:
                continue
            root = _match_known_root(decoded, known_roots) or _project_root_fallback(decoded)
            if root is not None:
                counts[root] = counts.get(root, 0) + 1
        if scanned > 4000:
            break
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def resolve_project_for_hash(
    hash_dir: Path, known_roots: list[str] | None = None
) -> str | None:
    """Best-effort project-folder resolution for a kiroagent workspace-hash dir.

    Resolution order (Requirement 13.2):
      1/2. ``documentUri`` in ``.json`` metadata files, matched against
           ``known_roots`` (or a coarse root) — reliable even when Session_Logs
           record no paths.
      3.   a ``file://`` reference in the largest extension-less Session_Logs.
    Returns ``None`` if no signal is found.
    """
    if known_roots is None:
        known_roots = []

    # Preference: documentUri in .json metadata files.
    root = _project_from_json_document_uris(hash_dir, known_roots)
    if root:
        return root

    # Fallback: file:// references inside the largest extension-less session logs.
    candidates: list[tuple[int, Path]] = []
    for dp, dirnames, filenames in os.walk(hash_dir):
        # Session logs never live inside an index/ subtree.
        dirnames[:] = [d for d in dirnames if d != "index"]
        for name in filenames:
            if os.path.splitext(name)[1] == "":
                p = Path(dp) / name
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                if size > 20_000:
                    candidates.append((size, p))
        if len(candidates) > 40:
            break

    candidates.sort(key=lambda t: t[0], reverse=True)
    for _, p in candidates[:8]:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:500_000]
        except OSError:
            continue
        root = _project_from_text(text, known_roots)
        if root:
            return root
    return None


def _hash_for_path(rel_path: Path) -> str | None:
    """Return the kiroagent workspace-hash component of a relative path, if any."""
    prefix_parts = Path(_KIROAGENT_PREFIX).parts
    parts = rel_path.parts
    if parts[: len(prefix_parts)] != prefix_parts:
        return None
    remainder = parts[len(prefix_parts):]
    if not remainder:
        return None
    return remainder[0]


def build_project_view(kiro_storage: Path, scan: ScanResult) -> ProjectView:
    """Group all scanned files by owning project folder.

    Every scanned file is placed in exactly one ProjectGroup. Files under a
    kiroagent workspace-hash dir are grouped by that hash's resolved project;
    the top-level kiroagent ``index/`` dir and everything outside the kiroagent
    tree are grouped under "(global)" (framework-level data); a hash dir with no
    recoverable project is grouped under "(unknown-project)". The sum of group
    totals equals the total scanned bytes (Property 17).
    """
    # Gather every scanned file with its category, from the flat scan result.
    all_files: list[tuple[Path, str]] = []
    for cat_name, cat_result in scan.categories.items():
        for f in cat_result.files:
            all_files.append((f, cat_name))
    for f in scan.uncategorized.files:
        all_files.append((f, "uncategorized"))

    # Resolve each distinct kiroagent hash once (attribution is per hash dir).
    kiroagent_root = kiro_storage / _KIROAGENT_PREFIX
    known_roots = known_project_roots(kiro_storage)
    hash_to_project: dict[str, str] = {}

    def project_for(rel_path: Path) -> str:
        h = _hash_for_path(rel_path)
        # Not under a workspace-hash dir (incl. the top-level shared index/):
        # framework-level data with no owning project.
        if h is None or h == "index":
            return GLOBAL_GROUP
        if h not in hash_to_project:
            resolved = resolve_project_for_hash(kiroagent_root / h, known_roots)
            hash_to_project[h] = resolved or UNKNOWN_PROJECT_GROUP
        return hash_to_project[h]

    groups: dict[str, ProjectGroup] = {}
    total_bytes = 0

    for path, category in all_files:
        try:
            st = path.stat()
        except OSError:
            continue
        size, mtime = st.st_size, st.st_mtime
        total_bytes += size

        try:
            rel = path.relative_to(kiro_storage)
        except ValueError:
            rel = Path(path.name)

        project = project_for(rel)
        group = groups.get(project)
        if group is None:
            group = ProjectGroup(project=project)
            groups[project] = group

        group.total_bytes += size
        group.category_bytes[category] = group.category_bytes.get(category, 0) + size
        if group.newest_mtime is None or mtime > group.newest_mtime:
            group.newest_mtime = mtime

        h = _hash_for_path(rel)
        if h and h != "index" and h not in group.workspace_hashes:
            group.workspace_hashes.append(h)

    ordered = sorted(groups.values(), key=lambda g: g.total_bytes, reverse=True)
    return ProjectView(groups=ordered, total_bytes=total_bytes)
