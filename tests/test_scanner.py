"""Unit tests for the scanner module."""

import os
from pathlib import Path

import pytest

from kiro_cleaner.scanner import (
    CategoryResult,
    ScanResult,
    _classify_file,
    format_size,
    scan_storage,
)


class TestClassifyFile:
    """Tests for the _classify_file function."""

    def test_logs_directory(self):
        assert _classify_file(Path("logs/2024-01-10.log")) == "logs"

    def test_logs_nested(self):
        assert _classify_file(Path("logs/subdir/file.txt")) == "logs"

    def test_cache_directory(self):
        assert _classify_file(Path("Cache/data_0")) == "cache"

    def test_cached_data_directory(self):
        assert _classify_file(Path("CachedData/index.json")) == "cache"

    def test_gpu_cache_directory(self):
        assert _classify_file(Path("GPUCache/gpu_data")) == "cache"

    def test_chats_file(self):
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/session1.chat")) == "chats"

    def test_chats_nested(self):
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/subdir/deep.chat")) == "chats"

    def test_index_directory(self):
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/index/vectors.bin")) == "index"

    def test_index_nested(self):
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/index/sub/data.bin")) == "index"

    def test_temp_extension_tmp(self):
        assert _classify_file(Path("some/path/file.tmp")) == "temp"

    def test_temp_extension_temp(self):
        assert _classify_file(Path("another/file.temp")) == "temp"

    def test_temp_case_insensitive(self):
        assert _classify_file(Path("file.TMP")) == "temp"

    def test_history_directory(self):
        assert _classify_file(Path("User/History/entry1.json")) == "history"

    def test_crash_reports_directory(self):
        assert _classify_file(Path("Crashpad/crash.dmp")) == "crash_reports"

    def test_uncategorized_file(self):
        assert _classify_file(Path("config.json")) == "uncategorized"

    def test_uncategorized_random_dir(self):
        assert _classify_file(Path("some/random/file.txt")) == "uncategorized"

    def test_directory_priority_over_temp(self):
        """A .tmp file under logs/ should go to logs (directory-based priority)."""
        assert _classify_file(Path("logs/debug.tmp")) == "logs"

    def test_directory_priority_temp_in_cache(self):
        """A .temp file under Cache/ should go to cache."""
        assert _classify_file(Path("Cache/data.temp")) == "cache"

    def test_index_priority_over_chats(self):
        """A .chat file under index/ should go to index."""
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/index/data.chat")) == "index"

    def test_non_chat_in_agent_dir(self):
        """A non-.chat file in kiro.kiroagent/ should be uncategorized."""
        assert _classify_file(Path("User/globalStorage/kiro.kiroagent/other.json")) == "uncategorized"


class TestFormatSize:
    """Tests for the format_size function."""

    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_one_byte(self):
        assert format_size(1) == "1 B"

    def test_bytes_range(self):
        assert format_size(512) == "512 B"

    def test_one_kb(self):
        assert format_size(1024) == "1 KB"

    def test_kilobytes(self):
        assert format_size(2048) == "2 KB"

    def test_fractional_kb(self):
        assert format_size(1536) == "1.5 KB"

    def test_one_mb(self):
        assert format_size(1024 * 1024) == "1 MB"

    def test_one_gb(self):
        assert format_size(1024**3) == "1 GB"

    def test_large_gb(self):
        assert format_size(5 * 1024**3) == "5 GB"

    def test_fractional_mb(self):
        # 1.5 MB = 1572864 bytes
        assert format_size(1572864) == "1.5 MB"

    def test_negative_treated_as_zero(self):
        assert format_size(-1) == "0 B"

    def test_1023_bytes(self):
        """1023 bytes should display as B since it's < 1 KB."""
        assert format_size(1023) == "1023 B"


class TestScanStorage:
    """Tests for the scan_storage function."""

    def test_scan_empty_storage(self, empty_kiro_storage):
        result = scan_storage(empty_kiro_storage)
        assert result.total_files == 0
        assert result.total_bytes == 0
        assert result.uncategorized.file_count == 0
        assert len(result.warnings) == 0

    def test_scan_categorizes_files(self, mock_kiro_storage):
        result = scan_storage(mock_kiro_storage)

        # logs/ has 2 log files + 1 .temp file (directory priority)
        assert result.categories["logs"].file_count == 3

        # Cache/ + CachedData/ + GPUCache/
        assert result.categories["cache"].file_count == 4

        # 2 .chat files
        assert result.categories["chats"].file_count == 2

        # index/ has 2 files
        assert result.categories["index"].file_count == 2

        # 1 .tmp file at root level (not under a categorized dir)
        assert result.categories["temp"].file_count == 1

        # User/History/ has 2 files
        assert result.categories["history"].file_count == 2

        # Crashpad/ has 1 file
        assert result.categories["crash_reports"].file_count == 1

    def test_scan_uncategorized(self, mock_kiro_storage):
        result = scan_storage(mock_kiro_storage)
        # config.json and settings.json at root are uncategorized
        assert result.uncategorized.file_count == 2

    def test_scan_total_invariant(self, mock_kiro_storage):
        """Total files should equal sum of all category counts + uncategorized."""
        result = scan_storage(mock_kiro_storage)
        category_total = sum(c.file_count for c in result.categories.values())
        assert result.total_files == category_total + result.uncategorized.file_count

    def test_scan_bytes_invariant(self, mock_kiro_storage):
        """Total bytes should equal sum of all category bytes + uncategorized."""
        result = scan_storage(mock_kiro_storage)
        category_bytes = sum(c.total_bytes for c in result.categories.values())
        assert result.total_bytes == category_bytes + result.uncategorized.total_bytes

    def test_scan_permission_error(self, tmp_path):
        """Permission errors should be captured as warnings."""
        storage = tmp_path / "storage"
        storage.mkdir()
        restricted = storage / "logs"
        restricted.mkdir()
        (restricted / "file.log").write_text("data")

        # Remove read permission on the directory
        os.chmod(restricted, 0o000)
        try:
            result = scan_storage(storage)
            assert len(result.warnings) > 0
            assert "Permission denied" in result.warnings[0]
        finally:
            # Restore permissions for cleanup
            os.chmod(restricted, 0o755)

    def test_scan_result_has_all_categories(self, empty_kiro_storage):
        result = scan_storage(empty_kiro_storage)
        expected_categories = {"logs", "cache", "chats", "index", "temp", "history", "crash_reports"}
        assert set(result.categories.keys()) == expected_categories

    def test_each_file_in_exactly_one_category(self, mock_kiro_storage):
        """No file should appear in multiple categories."""
        result = scan_storage(mock_kiro_storage)
        all_files: list[Path] = []
        for cat in result.categories.values():
            all_files.extend(cat.files)
        all_files.extend(result.uncategorized.files)

        # No duplicates
        assert len(all_files) == len(set(all_files))


# Feature: kiro-cleaner-python, Property 6: Size formatting correctness
from hypothesis import given, settings
from hypothesis import strategies as st


UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


@pytest.mark.property
@settings(max_examples=100)
@given(byte_count=st.integers(min_value=0, max_value=10 * 1024**3))
def test_format_size_correctness(byte_count: int):
    """
    **Validates: Requirements 1.2**

    For any non-negative integer byte count, the format_size function shall return
    a string using the largest unit (B, KB, MB, GB) where the numeric value is >= 1,
    and the formatted value when converted back to bytes (accounting for rounding)
    shall be within 1 unit of the original value.
    """
    result = format_size(byte_count)

    # Parse the result: should be "<number> <unit>"
    parts = result.split(" ")
    assert len(parts) == 2, f"Expected '<number> <unit>', got '{result}'"
    numeric_str, unit = parts[0], parts[1]

    # Unit must be valid
    assert unit in UNITS, f"Invalid unit '{unit}' in '{result}'"

    # Parse numeric value
    numeric_value = float(numeric_str)

    # The numeric value must be >= 1 (except for 0 B)
    if byte_count > 0:
        assert numeric_value >= 1.0, (
            f"Numeric value {numeric_value} < 1 for {byte_count} bytes (got '{result}')"
        )

    # Verify largest unit is used: no larger unit should give a value >= 1
    unit_order = ["GB", "MB", "KB", "B"]
    unit_index = unit_order.index(unit)
    for larger_unit in unit_order[:unit_index]:
        larger_unit_value = byte_count / UNITS[larger_unit]
        assert larger_unit_value < 1.0, (
            f"Larger unit '{larger_unit}' would give value {larger_unit_value} >= 1, "
            f"but format_size chose '{unit}' for {byte_count} bytes"
        )

    # Convert back to bytes and check rounding error is within 1 unit
    reconstructed_bytes = numeric_value * UNITS[unit]
    unit_size = UNITS[unit]
    error = abs(reconstructed_bytes - byte_count)
    assert error < unit_size, (
        f"Rounding error {error} >= unit size {unit_size} for {byte_count} bytes "
        f"(formatted as '{result}', reconstructed as {reconstructed_bytes})"
    )


# Feature: kiro-cleaner-python, Property 5: Scan total invariant
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Strategy to generate a random directory tree structure
# Each file is represented as (relative_path_parts, content_size)
@st.composite
def random_directory_tree(draw):
    """Generate a random directory tree specification.

    Returns a list of (path_parts_tuple, file_size) representing files to create.
    """
    # Possible directory prefixes that map to known categories
    category_dirs = [
        "logs",
        "Cache",
        "CachedData",
        "GPUCache",
        "User/History",
        "Crashpad",
        "User/globalStorage/kiro.kiroagent/index",
        "User/globalStorage/kiro.kiroagent",
    ]
    # Some uncategorized directories
    other_dirs = ["data", "misc", "User/other", ""]

    all_dirs = category_dirs + other_dirs

    # Generate a list of files
    num_files = draw(st.integers(min_value=0, max_value=20))
    files = []

    for _ in range(num_files):
        # Pick a directory
        dir_path = draw(st.sampled_from(all_dirs))

        # Generate a filename
        extensions = [".log", ".txt", ".json", ".bin", ".chat", ".tmp", ".temp", ".dat"]
        ext = draw(st.sampled_from(extensions))
        name = draw(st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
            min_size=1,
            max_size=10,
        ))
        filename = name + ext

        # Generate file size (0 to 10KB)
        size = draw(st.integers(min_value=0, max_value=10240))

        if dir_path:
            full_path = dir_path + "/" + filename
        else:
            full_path = filename

        files.append((full_path, size))

    return files


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(tree=random_directory_tree())
def test_scan_total_invariant_property(tmp_path_factory, tree):
    """Property 5: Scan total invariant.

    For any Kiro_Storage directory tree, the sum of file counts across all
    categories plus the uncategorized count shall equal the total file count,
    and the sum of byte sizes across all categories plus uncategorized bytes
    shall equal the total bytes reported.

    **Validates: Requirements 1.6**
    """
    # Create a temporary directory for this test instance
    storage = tmp_path_factory.mktemp("kiro_storage")

    # Build the directory tree from the generated specification
    for file_path, size in tree:
        full_path = storage / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"\x00" * size)

    # Run the scanner
    result = scan_storage(storage)

    # Assert file count invariant:
    # sum(category.file_count for all categories) + uncategorized.file_count == total_files
    category_file_count = sum(c.file_count for c in result.categories.values())
    assert category_file_count + result.uncategorized.file_count == result.total_files

    # Assert byte size invariant:
    # sum(category.total_bytes for all categories) + uncategorized.total_bytes == total_bytes
    category_bytes = sum(c.total_bytes for c in result.categories.values())
    assert category_bytes + result.uncategorized.total_bytes == result.total_bytes


# Feature: kiro-cleaner-python, Property 4: Scan categorization correctness
# Validates: Requirements 1.1
from hypothesis import given, settings
from hypothesis import strategies as st


def _safe_path_segment():
    """Generate a safe path segment (no slashes, not empty, no dots-only)."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Pd"),
            whitelist_characters="_-",
        ),
        min_size=1,
        max_size=20,
    ).filter(lambda s: s not in (".", ".."))


def _safe_filename(extension=None):
    """Generate a safe filename with optional fixed extension."""
    base = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="_-",
        ),
        min_size=1,
        max_size=15,
    )
    if extension:
        return base.map(lambda b: f"{b}{extension}")
    # Generate a filename with a non-temp extension
    ext = st.sampled_from([".log", ".json", ".bin", ".dat", ".txt", ".db", ".xml"])
    return st.tuples(base, ext).map(lambda t: f"{t[0]}{t[1]}")


def _subdirs():
    """Generate 0-2 subdirectory segments."""
    return st.lists(_safe_path_segment(), min_size=0, max_size=2)


@st.composite
def logs_path_strategy(draw):
    """Generate paths under logs/ directory."""
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename())
    parts = ["logs"] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def cache_path_strategy(draw):
    """Generate paths under Cache/, CachedData/, or GPUCache/ directories."""
    cache_dir = draw(st.sampled_from(["Cache", "CachedData", "GPUCache"]))
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename())
    parts = [cache_dir] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def chats_path_strategy(draw):
    """Generate paths matching User/globalStorage/kiro.kiroagent/**/*.chat."""
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename(".chat"))
    parts = ["User", "globalStorage", "kiro.kiroagent"] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def index_path_strategy(draw):
    """Generate paths under User/globalStorage/kiro.kiroagent/index/."""
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename())
    parts = ["User", "globalStorage", "kiro.kiroagent", "index"] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def temp_path_strategy(draw):
    """Generate paths with .tmp or .temp extension not under categorized dirs."""
    ext = draw(st.sampled_from([".tmp", ".temp", ".TMP", ".TEMP", ".Tmp"]))
    # Use a prefix that doesn't match any directory-based category
    prefix_dir = draw(st.sampled_from(["some", "other", "random", "data", "workspace"]))
    subdirs = draw(_subdirs())
    base = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=15,
    ))
    parts = [prefix_dir] + subdirs + [f"{base}{ext}"]
    return "/".join(parts)


@st.composite
def history_path_strategy(draw):
    """Generate paths under User/History/ directory."""
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename())
    parts = ["User", "History"] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def crash_reports_path_strategy(draw):
    """Generate paths under Crashpad/ directory."""
    subdirs = draw(_subdirs())
    filename = draw(_safe_filename())
    parts = ["Crashpad"] + subdirs + [filename]
    return "/".join(parts)


@st.composite
def uncategorized_path_strategy(draw):
    """Generate paths that don't match any category."""
    # Use directory names that don't match any category prefix
    prefix = draw(st.sampled_from([
        "extensions", "data", "workspace", "profiles", "snippets",
        "backups", "plugins", "themes", "keybindings",
    ]))
    subdirs = draw(_subdirs())
    # Use extensions that are not .tmp or .temp or .chat
    ext = draw(st.sampled_from([".json", ".log", ".bin", ".dat", ".txt", ".db", ".xml", ".yaml"]))
    base = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=15,
    ))
    parts = [prefix] + subdirs + [f"{base}{ext}"]
    return "/".join(parts)


class TestScanCategorizationProperty:
    """Property 4: Scan categorization correctness.

    For any file within the Kiro_Storage directory tree, the scanner shall classify
    it into exactly one category based on its path.
    """

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=logs_path_strategy())
    def test_logs_categorization(self, path_str):
        """Files under logs/ are classified as logs."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "logs", f"Expected 'logs' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=cache_path_strategy())
    def test_cache_categorization(self, path_str):
        """Files under Cache/, CachedData/, or GPUCache/ are classified as cache."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "cache", f"Expected 'cache' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=chats_path_strategy())
    def test_chats_categorization(self, path_str):
        """Files matching User/globalStorage/kiro.kiroagent/**/*.chat are classified as chats."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "chats", f"Expected 'chats' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=index_path_strategy())
    def test_index_categorization(self, path_str):
        """Files under User/globalStorage/kiro.kiroagent/index/ are classified as index."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "index", f"Expected 'index' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=temp_path_strategy())
    def test_temp_categorization(self, path_str):
        """Files with .tmp or .temp extension (not under categorized dirs) are classified as temp."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "temp", f"Expected 'temp' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=history_path_strategy())
    def test_history_categorization(self, path_str):
        """Files under User/History/ are classified as history."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "history", f"Expected 'history' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=crash_reports_path_strategy())
    def test_crash_reports_categorization(self, path_str):
        """Files under Crashpad/ are classified as crash_reports."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "crash_reports", f"Expected 'crash_reports' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=uncategorized_path_strategy())
    def test_uncategorized_classification(self, path_str):
        """Files not matching any category are classified as uncategorized."""
        # Validates: Requirements 1.1
        result = _classify_file(Path(path_str))
        assert result == "uncategorized", f"Expected 'uncategorized' for path '{path_str}', got '{result}'"

    @pytest.mark.property
    @settings(max_examples=100)
    @given(path_str=st.one_of(
        logs_path_strategy(),
        cache_path_strategy(),
        chats_path_strategy(),
        index_path_strategy(),
        temp_path_strategy(),
        history_path_strategy(),
        crash_reports_path_strategy(),
        uncategorized_path_strategy(),
    ))
    def test_exactly_one_category(self, path_str):
        """Every file is classified into exactly one category (never None or empty)."""
        # Validates: Requirements 1.1
        valid_categories = {"logs", "cache", "chats", "index", "temp", "history", "crash_reports", "uncategorized"}
        result = _classify_file(Path(path_str))
        assert result in valid_categories, f"Got unexpected category '{result}' for path '{path_str}'"
