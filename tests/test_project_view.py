"""Tests for the project_view module (project-aggregated view)."""

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kiro_cleaner.project_view import (
    ProjectGroup,
    ProjectView,
    _project_root_fallback,
    build_project_view,
    resolve_project_for_hash,
)
from kiro_cleaner.scanner import scan_storage


class TestProjectRoot:
    """Tests for reducing a file path to its coarse project root (fallback)."""

    def test_three_segment_root(self):
        assert _project_root_fallback("/Users/alice/myproject/src/main.py") == "/Users/alice/myproject"

    def test_exactly_three_segments(self):
        assert _project_root_fallback("/Users/alice/myproject") == "/Users/alice/myproject"

    def test_too_shallow_returns_none(self):
        assert _project_root_fallback("/Users/alice") is None

    def test_trailing_slash_ignored(self):
        assert _project_root_fallback("/Users/alice/proj/") == "/Users/alice/proj"


class TestResolveProjectForHash:
    """Tests for resolving a kiroagent hash dir to a project folder."""

    def _make_session_log(self, path: Path, project_file: str) -> None:
        # A session log large enough (>20KB) to be sampled, referencing a project.
        payload = {
            "executionId": "x",
            "workflowType": "act",
            "documentUri": f"file://{project_file}",
            "padding": "z" * 30000,
        }
        path.write_text(json.dumps(payload))

    def test_resolves_from_session_log_with_known_root(self, tmp_path):
        """With a known workspace folder, resolution is depth-aware."""
        hash_dir = tmp_path / "hash1"
        sub = hash_dir / "sub"
        sub.mkdir(parents=True)
        self._make_session_log(sub / "logfile", "/Users/tester/projects/demo/requirements.md")

        result = resolve_project_for_hash(hash_dir, ["/Users/tester/projects/demo"])
        assert result == "/Users/tester/projects/demo"

    def test_resolves_from_session_log_fallback(self, tmp_path):
        """Without a known folder, resolution falls back to a coarse 3-segment root."""
        hash_dir = tmp_path / "hash1b"
        sub = hash_dir / "sub"
        sub.mkdir(parents=True)
        self._make_session_log(sub / "logfile", "/Users/tester/projects/demo/requirements.md")

        assert resolve_project_for_hash(hash_dir) == "/Users/tester/projects"

    def test_unresolved_when_no_session_logs(self, tmp_path):
        hash_dir = tmp_path / "hash2"
        hash_dir.mkdir()
        (hash_dir / "tiny").write_text("no uri here")

        assert resolve_project_for_hash(hash_dir) is None

    def test_ignores_index_subtree(self, tmp_path):
        hash_dir = tmp_path / "hash3"
        index_dir = hash_dir / "index"
        index_dir.mkdir(parents=True)
        # A big file with a URI, but inside index/ — must be ignored.
        self._make_session_log(index_dir / "segment", "/Users/tester/should_not/use_me.py")

        assert resolve_project_for_hash(hash_dir) is None


class TestBuildProjectView:
    """Tests for build_project_view over a real scanned tree."""

    def test_partition_matches_scan_total(self, mock_kiro_storage):
        scan = scan_storage(mock_kiro_storage)
        view = build_project_view(mock_kiro_storage, scan)

        assert view.total_bytes == scan.total_bytes
        assert sum(g.total_bytes for g in view.groups) == scan.total_bytes

    def test_category_bytes_sum_to_group_total(self, mock_kiro_storage):
        scan = scan_storage(mock_kiro_storage)
        view = build_project_view(mock_kiro_storage, scan)

        for group in view.groups:
            assert sum(group.category_bytes.values()) == group.total_bytes

    def test_groups_sorted_by_size_desc(self, mock_kiro_storage):
        scan = scan_storage(mock_kiro_storage)
        view = build_project_view(mock_kiro_storage, scan)

        sizes = [g.total_bytes for g in view.groups]
        assert sizes == sorted(sizes, reverse=True)

    def test_session_hash_resolves_to_project(self, mock_kiro_storage):
        # The conftest workspace-hash dir references /Users/tester/projects/demo.
        scan = scan_storage(mock_kiro_storage)
        view = build_project_view(mock_kiro_storage, scan)
        projects = {g.project for g in view.groups}
        assert "/Users/tester/projects/demo" in projects


# Feature: kiro-cleaner-python, Property 17: Project-view partition invariant


@st.composite
def project_storage_tree(draw):
    """Generate a spec of files under a mock kiro storage tree.

    Returns a list of (relative_path, size) covering categorized dirs, kiroagent
    session logs / index, and uncategorized files.
    """
    dirs = [
        "logs",
        "Cache",
        "User/History",
        "Crashpad",
        "User/globalStorage/kiro.kiroagent",  # chats go here (.chat)
        "User/globalStorage/kiro.kiroagent/deadbeefdeadbeef/inner",  # sessions
        "User/globalStorage/kiro.kiroagent/deadbeefdeadbeef/index",  # per-ws index
        "User/globalStorage/kiro.kiroagent/index",  # top-level index
        "misc",
    ]
    num = draw(st.integers(min_value=0, max_value=15))
    files = []
    for _ in range(num):
        d = draw(st.sampled_from(dirs))
        ext = draw(st.sampled_from([".log", ".chat", ".bin", "", ".txt", ".tmp"]))
        base = draw(st.text(alphabet="abcdef0123456789", min_size=1, max_size=10))
        size = draw(st.integers(min_value=0, max_value=4096))
        rel = f"{d}/{base}{ext}" if d else f"{base}{ext}"
        files.append((rel, size))
    return files


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(tree=project_storage_tree())
def test_project_view_partition_invariant(tmp_path_factory, tree):
    """Property 17: Project-view partition invariant.

    The sum of every group's total_bytes (including the "(unresolved)" group)
    equals the total scanned bytes, and each group's per-Category byte breakdown
    sums to that group's total_bytes.

    **Validates: Requirements 13.1, 13.3, 13.4**
    """
    storage = tmp_path_factory.mktemp("kiro_storage")
    for rel, size in tree:
        p = storage / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00" * size)

    scan = scan_storage(storage)
    view = build_project_view(storage, scan)

    # Partition invariant: group totals sum to scan total.
    assert sum(g.total_bytes for g in view.groups) == scan.total_bytes
    assert view.total_bytes == scan.total_bytes

    # Each group's category breakdown sums to its total.
    for group in view.groups:
        assert sum(group.category_bytes.values()) == group.total_bytes
