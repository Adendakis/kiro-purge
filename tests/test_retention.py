"""Tests for the retention filter module."""

import os
import time
from pathlib import Path

import pytest

from kiro_cleaner.retention import DEFAULT_RETENTION, filter_by_retention


class TestDefaultRetention:
    """Tests for the DEFAULT_RETENTION dictionary."""

    def test_logs_retention_is_7_days(self):
        assert DEFAULT_RETENTION["logs"] == 7

    def test_crash_reports_retention_is_30_days(self):
        assert DEFAULT_RETENTION["crash_reports"] == 30

    def test_history_retention_is_30_days(self):
        assert DEFAULT_RETENTION["history"] == 30

    def test_chats_retention_is_30_days(self):
        assert DEFAULT_RETENTION["chats"] == 30

    def test_cache_retention_is_0(self):
        assert DEFAULT_RETENTION["cache"] == 0

    def test_temp_retention_is_0(self):
        assert DEFAULT_RETENTION["temp"] == 0

    def test_index_retention_is_0(self):
        assert DEFAULT_RETENTION["index"] == 0

    def test_all_categories_present(self):
        expected_keys = {"logs", "crash_reports", "history", "chats", "cache", "temp", "index"}
        assert set(DEFAULT_RETENTION.keys()) == expected_keys


class TestFilterByRetentionAlwaysEligible:
    """Tests for categories that always return all files (cache, temp, index)."""

    def test_cache_returns_all_files(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"data_{i}"
            f.write_bytes(b"\x00" * 10)
            files.append(f)

        result = filter_by_retention(files, "cache")
        assert result == files

    def test_temp_returns_all_files(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.tmp"
            f.write_bytes(b"\x00" * 10)
            files.append(f)

        result = filter_by_retention(files, "temp")
        assert result == files

    def test_index_returns_all_files(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"index_{i}.bin"
            f.write_bytes(b"\x00" * 10)
            files.append(f)

        result = filter_by_retention(files, "index")
        assert result == files

    def test_cache_ignores_keep_recent_days(self, tmp_path):
        f = tmp_path / "recent_cache"
        f.write_bytes(b"\x00" * 10)

        result = filter_by_retention([f], "cache", keep_recent_days=9999)
        assert result == [f]

    def test_temp_ignores_keep_recent_days(self, tmp_path):
        f = tmp_path / "recent.tmp"
        f.write_bytes(b"\x00" * 10)

        result = filter_by_retention([f], "temp", keep_recent_days=9999)
        assert result == [f]

    def test_index_ignores_keep_recent_days(self, tmp_path):
        f = tmp_path / "recent_index"
        f.write_bytes(b"\x00" * 10)

        result = filter_by_retention([f], "index", keep_recent_days=9999)
        assert result == [f]

    def test_empty_file_list_returns_empty(self):
        result = filter_by_retention([], "cache")
        assert result == []


class TestFilterByRetentionTimeBased:
    """Tests for categories with time-based retention (logs, crash_reports, history, chats)."""

    def test_old_log_file_is_eligible(self, tmp_path):
        f = tmp_path / "old.log"
        f.write_text("old log")
        # Set mtime to 10 days ago
        old_time = time.time() - (10 * 86400)
        os.utime(f, (old_time, old_time))

        result = filter_by_retention([f], "logs")
        assert f in result

    def test_recent_log_file_is_not_eligible(self, tmp_path):
        f = tmp_path / "recent.log"
        f.write_text("recent log")
        # File was just created, so mtime is now

        result = filter_by_retention([f], "logs")
        assert f not in result

    def test_file_just_within_retention_is_not_eligible(self, tmp_path):
        f = tmp_path / "boundary.log"
        f.write_text("boundary log")
        # Set mtime to 6 days ago (within 7-day retention)
        within_time = time.time() - (6 * 86400)
        os.utime(f, (within_time, within_time))

        # File is within retention period, so not eligible
        result = filter_by_retention([f], "logs")
        assert f not in result

    def test_crash_reports_30_day_retention(self, tmp_path):
        old_file = tmp_path / "old_crash.dmp"
        old_file.write_bytes(b"\x00" * 10)
        old_time = time.time() - (31 * 86400)
        os.utime(old_file, (old_time, old_time))

        recent_file = tmp_path / "recent_crash.dmp"
        recent_file.write_bytes(b"\x00" * 10)

        result = filter_by_retention([old_file, recent_file], "crash_reports")
        assert old_file in result
        assert recent_file not in result

    def test_history_30_day_retention(self, tmp_path):
        old_file = tmp_path / "old_history.json"
        old_file.write_text("{}")
        old_time = time.time() - (31 * 86400)
        os.utime(old_file, (old_time, old_time))

        result = filter_by_retention([old_file], "history")
        assert old_file in result

    def test_chats_30_day_retention(self, tmp_path):
        old_file = tmp_path / "old.chat"
        old_file.write_text("{}")
        old_time = time.time() - (31 * 86400)
        os.utime(old_file, (old_time, old_time))

        result = filter_by_retention([old_file], "chats")
        assert old_file in result

    def test_keep_recent_days_overrides_default(self, tmp_path):
        # File is 5 days old - normally within 7-day log retention
        f = tmp_path / "medium_age.log"
        f.write_text("log")
        medium_time = time.time() - (5 * 86400)
        os.utime(f, (medium_time, medium_time))

        # With default retention (7 days), file is NOT eligible
        result = filter_by_retention([f], "logs")
        assert f not in result

        # With keep_recent_days=3, file IS eligible (older than 3 days)
        result = filter_by_retention([f], "logs", keep_recent_days=3)
        assert f in result

    def test_keep_recent_days_can_extend_retention(self, tmp_path):
        # File is 10 days old - normally eligible for log deletion (>7 days)
        f = tmp_path / "ten_days.log"
        f.write_text("log")
        old_time = time.time() - (10 * 86400)
        os.utime(f, (old_time, old_time))

        # With keep_recent_days=15, file is NOT eligible (within 15 days)
        result = filter_by_retention([f], "logs", keep_recent_days=15)
        assert f not in result

    def test_empty_file_list_returns_empty(self):
        result = filter_by_retention([], "logs")
        assert result == []

    def test_nonexistent_file_is_skipped(self, tmp_path):
        nonexistent = tmp_path / "ghost.log"
        result = filter_by_retention([nonexistent], "logs")
        assert result == []

    def test_mixed_old_and_new_files(self, tmp_path):
        old_files = []
        new_files = []

        for i in range(3):
            f = tmp_path / f"old_{i}.log"
            f.write_text(f"old log {i}")
            old_time = time.time() - (10 * 86400)
            os.utime(f, (old_time, old_time))
            old_files.append(f)

        for i in range(2):
            f = tmp_path / f"new_{i}.log"
            f.write_text(f"new log {i}")
            new_files.append(f)

        all_files = old_files + new_files
        result = filter_by_retention(all_files, "logs")

        for f in old_files:
            assert f in result
        for f in new_files:
            assert f not in result


# Feature: kiro-cleaner-python, Property 3: Retention filter correctness

import tempfile

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# Categories that are always eligible for deletion regardless of age
ALWAYS_ELIGIBLE_CATEGORIES = ["cache", "temp", "index"]

# Categories with time-based retention
TIME_BASED_CATEGORIES = ["logs", "crash_reports", "history", "chats"]

# Default retention days per time-based category
TIME_BASED_RETENTION = {
    "logs": 7,
    "crash_reports": 30,
    "history": 30,
    "chats": 30,
}


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    age_days=st.floats(min_value=0.0, max_value=365.0, allow_nan=False, allow_infinity=False),
    category=st.sampled_from(ALWAYS_ELIGIBLE_CATEGORIES),
    keep_recent_days=st.one_of(st.none(), st.integers(min_value=1, max_value=365)),
)
def test_always_eligible_categories_return_all_files(age_days, category, keep_recent_days):
    """
    **Validates: Requirements 3.7**

    For temp, cache, and index categories, all files are always eligible
    regardless of age or --keep-recent value.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "testfile"
        f.write_bytes(b"\x00" * 10)

        # Set modification time to age_days ago
        mtime = time.time() - (age_days * 86400)
        os.utime(f, (mtime, mtime))

        result = filter_by_retention([f], category, keep_recent_days=keep_recent_days)
        assert f in result, (
            f"File with age {age_days} days in category '{category}' "
            f"should always be eligible, but was not returned"
        )


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    age_days=st.floats(min_value=0.0, max_value=365.0, allow_nan=False, allow_infinity=False),
    category=st.sampled_from(TIME_BASED_CATEGORIES),
)
def test_time_based_categories_default_retention(age_days, category):
    """
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

    For time-based categories, a file is eligible for deletion if and only if
    its modification time is strictly older than the retention threshold.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "testfile"
        f.write_bytes(b"\x00" * 10)

        # Set modification time to age_days ago
        mtime = time.time() - (age_days * 86400)
        os.utime(f, (mtime, mtime))

        retention_days = TIME_BASED_RETENTION[category]
        result = filter_by_retention([f], category)

        if age_days > retention_days:
            assert f in result, (
                f"File aged {age_days} days in '{category}' (retention={retention_days}) "
                f"should be eligible for deletion"
            )
        else:
            assert f not in result, (
                f"File aged {age_days} days in '{category}' (retention={retention_days}) "
                f"should NOT be eligible for deletion"
            )


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    age_days=st.floats(min_value=0.0, max_value=365.0, allow_nan=False, allow_infinity=False),
    category=st.sampled_from(TIME_BASED_CATEGORIES),
    keep_recent_days=st.integers(min_value=1, max_value=365),
)
def test_keep_recent_overrides_default_retention(age_days, category, keep_recent_days):
    """
    **Validates: Requirements 3.5**

    When --keep-recent N is specified, the threshold is overridden to N days
    for time-based categories.
    """
    # Avoid the exact boundary where timing races make the test flaky.
    # A small epsilon (1 second expressed in days) avoids the race between
    # setting mtime and the implementation calling time.time().
    epsilon = 1.0 / 86400.0  # 1 second in days
    assume(abs(age_days - keep_recent_days) > epsilon)

    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "testfile"
        f.write_bytes(b"\x00" * 10)

        # Set modification time to age_days ago
        mtime = time.time() - (age_days * 86400)
        os.utime(f, (mtime, mtime))

        result = filter_by_retention([f], category, keep_recent_days=keep_recent_days)

        if age_days > keep_recent_days:
            assert f in result, (
                f"File aged {age_days} days in '{category}' with keep_recent={keep_recent_days} "
                f"should be eligible for deletion"
            )
        else:
            assert f not in result, (
                f"File aged {age_days} days in '{category}' with keep_recent={keep_recent_days} "
                f"should NOT be eligible for deletion"
            )
