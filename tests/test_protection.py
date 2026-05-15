"""Unit tests for the protection guard module."""

from pathlib import Path

from kiro_cleaner.protection import (
    PROTECTED_DIRECTORIES,
    PROTECTED_FILES,
    is_protected,
)


class TestProtectedSets:
    """Tests for the protected files and directories sets."""

    def test_protected_files_contains_all_required(self):
        expected = {
            "config.json",
            "settings.json",
            "mcp.json",
            "sessions.json",
            "state.vscdb",
            "workspace.json",
            "storage.json",
        }
        assert PROTECTED_FILES == expected

    def test_protected_directories_contains_all_required(self):
        expected = {"index", ".migrations", "lancedb"}
        assert PROTECTED_DIRECTORIES == expected


class TestIsProtected:
    """Tests for the is_protected function."""

    def test_protected_file_at_root(self):
        result, reason = is_protected(Path("config.json"))
        assert result is True
        assert reason is not None
        assert "config.json" in reason

    def test_protected_file_in_subdirectory(self):
        result, reason = is_protected(Path("some/nested/dir/settings.json"))
        assert result is True
        assert "settings.json" in reason

    def test_all_protected_files_detected(self):
        for filename in PROTECTED_FILES:
            result, reason = is_protected(Path(f"any/path/{filename}"))
            assert result is True, f"{filename} should be protected"
            assert reason is not None

    def test_protected_directory_in_path(self):
        result, reason = is_protected(Path("User/globalStorage/kiro.kiroagent/index/data.bin"))
        assert result is True
        assert "index" in reason

    def test_migrations_directory_protected(self):
        result, reason = is_protected(Path(".migrations/001.sql"))
        assert result is True
        assert ".migrations" in reason

    def test_lancedb_directory_protected(self):
        result, reason = is_protected(Path("data/lancedb/vectors.lance"))
        assert result is True
        assert "lancedb" in reason

    def test_all_protected_directories_detected(self):
        for dirname in PROTECTED_DIRECTORIES:
            result, reason = is_protected(Path(f"root/{dirname}/somefile.txt"))
            assert result is True, f"Files in {dirname}/ should be protected"
            assert reason is not None

    def test_unprotected_file(self):
        result, reason = is_protected(Path("logs/2024-01-10.log"))
        assert result is False
        assert reason is None

    def test_unprotected_temp_file(self):
        result, reason = is_protected(Path("Cache/data_0"))
        assert result is False
        assert reason is None

    def test_similar_but_not_protected_filename(self):
        # "config.yaml" is not in the protected set
        result, reason = is_protected(Path("config.yaml"))
        assert result is False
        assert reason is None

    def test_similar_but_not_protected_directory(self):
        # "indexes" is not "index"
        result, reason = is_protected(Path("indexes/data.bin"))
        assert result is False
        assert reason is None

    def test_protected_file_takes_priority_over_directory(self):
        # A protected file inside a non-protected directory
        result, reason = is_protected(Path("logs/config.json"))
        assert result is True
        assert "config.json" in reason

    def test_file_in_nested_protected_directory(self):
        # Deep nesting within a protected directory
        result, reason = is_protected(Path("a/b/lancedb/c/d/file.dat"))
        assert result is True
        assert "lancedb" in reason

    def test_absolute_path_with_protected_file(self):
        result, reason = is_protected(Path("/home/user/kiro/storage/mcp.json"))
        assert result is True
        assert "mcp.json" in reason

    def test_absolute_path_with_protected_directory(self):
        result, reason = is_protected(Path("/home/user/kiro/.migrations/data.sql"))
        assert result is True
        assert ".migrations" in reason


# Feature: kiro-cleaner-python, Property 2: Protection invariant
# Validates: Requirements 2.5, 4.1, 4.2, 4.3, 4.4, 4.6

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Strategies for generating path components
_safe_path_chars = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_.",
    ),
    min_size=1,
    max_size=20,
)

# Strategy for a filename that is NOT in PROTECTED_FILES and NOT in PROTECTED_DIRECTORIES
_non_protected_filename = _safe_path_chars.filter(
    lambda name: name not in PROTECTED_FILES and name not in PROTECTED_DIRECTORIES
)

# Strategy for a directory component that is NOT in PROTECTED_DIRECTORIES and NOT in PROTECTED_FILES
_non_protected_dir = _safe_path_chars.filter(
    lambda name: name not in PROTECTED_DIRECTORIES and name not in PROTECTED_FILES
)


@st.composite
def path_with_protected_file(draw):
    """Generate a random file path whose filename is a protected file."""
    protected_name = draw(st.sampled_from(sorted(PROTECTED_FILES)))
    num_dirs = draw(st.integers(min_value=0, max_value=5))
    dirs = [draw(_non_protected_dir) for _ in range(num_dirs)]
    parts = dirs + [protected_name]
    return Path(*parts) if len(parts) > 1 else Path(parts[0])


@st.composite
def path_with_protected_directory(draw):
    """Generate a random file path that contains a protected directory component."""
    protected_dir = draw(st.sampled_from(sorted(PROTECTED_DIRECTORIES)))
    # Generate prefix directories (0-3 levels before the protected dir)
    num_prefix = draw(st.integers(min_value=0, max_value=3))
    prefix = [draw(_non_protected_dir) for _ in range(num_prefix)]
    # Generate suffix (at least one file after the protected dir)
    num_suffix_dirs = draw(st.integers(min_value=0, max_value=2))
    suffix_dirs = [draw(_non_protected_dir) for _ in range(num_suffix_dirs)]
    filename = draw(_non_protected_filename)
    parts = prefix + [protected_dir] + suffix_dirs + [filename]
    return Path(*parts)


@st.composite
def path_without_protection(draw):
    """Generate a random file path that does NOT contain any protected file or directory."""
    num_dirs = draw(st.integers(min_value=1, max_value=5))
    dirs = [draw(_non_protected_dir) for _ in range(num_dirs)]
    filename = draw(_non_protected_filename)
    parts = dirs + [filename]
    return Path(*parts)


@pytest.mark.property
class TestProtectionInvariantProperty:
    """Property-based tests for the protection invariant.

    Property 2: For any file path, if the filename matches any entry in the
    Protected_Files set OR if any component of the path matches a Protected_Directory
    name, then the cleaner shall skip that file and never delete it, regardless of
    which categories are selected, which flags are provided (including --force), or
    which operation is executing.
    """

    @given(path=path_with_protected_file())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_protected_file_always_detected(self, path: Path):
        """Any path whose filename is in PROTECTED_FILES must be protected."""
        protected, reason = is_protected(path)
        assert protected is True, f"Path {path} should be protected (filename: {path.name})"
        assert reason is not None

    @given(path=path_with_protected_directory())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_protected_directory_always_detected(self, path: Path):
        """Any path containing a protected directory component must be protected."""
        protected, reason = is_protected(path)
        assert protected is True, f"Path {path} should be protected (has protected dir)"
        assert reason is not None

    @given(path=path_without_protection())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_protected_path_not_flagged(self, path: Path):
        """Any path without protected filenames or directories must NOT be protected."""
        protected, reason = is_protected(path)
        assert protected is False, f"Path {path} should NOT be protected"
        assert reason is None
