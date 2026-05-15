"""Property-based tests for the cleaner engine."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from kiro_cleaner.cleaner import clean_files, CleanResult
from kiro_cleaner.protection import PROTECTED_FILES, PROTECTED_DIRECTORIES


# Feature: kiro-cleaner-python, Property 7: Dry-run no-deletion invariant
# **Validates: Requirements 2.6**


# Strategy: generate a list of filenames (simple safe names)
# Use only lowercase ASCII to avoid case-insensitive filesystem collisions (macOS HFS+)
_safe_filename_chars = st.text(
    alphabet=st.characters(
        whitelist_categories=("Nd",),  # digits
        whitelist_characters="abcdefghijklmnopqrstuvwxyz-_",
    ),
    min_size=1,
    max_size=20,
)

# Strategy: generate random file content (binary)
_file_content = st.binary(min_size=0, max_size=1024)


@st.composite
def temp_files_strategy(draw):
    """Generate a list of (filename, content) pairs for creating temp files.

    Filenames are guaranteed unique and avoid protected file names.
    """
    num_files = draw(st.integers(min_value=1, max_value=10))
    files = []
    seen_names = set()

    for _ in range(num_files):
        name = draw(_safe_filename_chars.filter(
            lambda n: n not in PROTECTED_FILES
            and n not in PROTECTED_DIRECTORIES
            and n not in seen_names
        ))
        seen_names.add(name)
        content = draw(_file_content)
        files.append((name, content))

    return files


@pytest.mark.property
class TestDryRunNoDeletionInvariant:
    """Property-based tests for the dry-run no-deletion invariant.

    Property 7: For any set of files targeted for cleaning, when the --dry-run
    flag is active, the cleaner shall report all targeted files but the file
    system shall remain unchanged (no files deleted, no directories removed,
    no archives created).
    """

    @given(file_specs=temp_files_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_dry_run_preserves_all_files(self, file_specs, tmp_path):
        """In dry-run mode, all files must still exist after clean_files is called."""
        # Create temp files with random content
        file_paths = []
        for name, content in file_specs:
            file_path = tmp_path / name
            file_path.write_bytes(content)
            file_paths.append(file_path)

        # Record state before dry-run
        files_before = {p: p.read_bytes() for p in file_paths}

        # Call clean_files with dry_run=True
        result = clean_files(file_paths, dry_run=True)

        # Assert all files still exist with unchanged content
        for file_path, original_content in files_before.items():
            assert file_path.exists(), f"File {file_path} was deleted during dry-run"
            assert file_path.read_bytes() == original_content, (
                f"File {file_path} content was modified during dry-run"
            )

    @given(file_specs=temp_files_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_dry_run_reports_correct_count(self, file_specs, tmp_path):
        """In dry-run mode, the result must report the correct count of targeted files."""
        # Create temp files with random content
        file_paths = []
        for name, content in file_specs:
            file_path = tmp_path / name
            file_path.write_bytes(content)
            file_paths.append(file_path)

        # Call clean_files with dry_run=True
        result = clean_files(file_paths, dry_run=True)

        # The deleted_count should equal the number of non-protected, existing files
        assert result.deleted_count == len(file_paths), (
            f"Expected {len(file_paths)} reported deletions, got {result.deleted_count}"
        )

    @given(file_specs=temp_files_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_dry_run_reports_correct_bytes(self, file_specs, tmp_path):
        """In dry-run mode, the result must report the correct total bytes."""
        # Create temp files with random content
        file_paths = []
        expected_bytes = 0
        for name, content in file_specs:
            file_path = tmp_path / name
            file_path.write_bytes(content)
            file_paths.append(file_path)
            expected_bytes += len(content)

        # Call clean_files with dry_run=True
        result = clean_files(file_paths, dry_run=True)

        # The deleted_bytes should equal the sum of all file sizes
        assert result.deleted_bytes == expected_bytes, (
            f"Expected {expected_bytes} bytes reported, got {result.deleted_bytes}"
        )

    @given(file_specs=temp_files_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_dry_run_no_directories_removed(self, file_specs, tmp_path):
        """In dry-run mode, no directories should be removed."""
        # Create a subdirectory structure with files
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir(exist_ok=True)

        file_paths = []
        for name, content in file_specs:
            file_path = sub_dir / name
            file_path.write_bytes(content)
            file_paths.append(file_path)

        # Call clean_files with dry_run=True
        result = clean_files(file_paths, dry_run=True)

        # Assert the directory still exists
        assert sub_dir.exists(), "Directory was removed during dry-run"
        assert sub_dir.is_dir(), "Directory was replaced during dry-run"


# Feature: kiro-cleaner-python, Property 14: Error classification correctness
# **Validates: Requirements 10.2**

import errno
from unittest.mock import patch

from kiro_cleaner.cleaner import ErrorType, DeletionError


# Strategy for generating various OSError subtypes with errno values
_errno_values = st.sampled_from([
    errno.EIO,
    errno.ENOSPC,
    errno.EROFS,
    errno.EBUSY,
    errno.ENOMEM,
    errno.ENODEV,
    errno.EISDIR,
    errno.EINVAL,
    errno.EMFILE,
    errno.ENFILE,
])

# Strategy for error types to raise during file deletion
_error_strategy = st.one_of(
    st.just("permission"),
    st.just("not_found"),
    st.tuples(st.just("other"), _errno_values),
)


def _make_exception(error_spec):
    """Create an exception instance from an error specification."""
    if error_spec == "permission":
        return PermissionError(errno.EACCES, "Permission denied")
    elif error_spec == "not_found":
        return FileNotFoundError(errno.ENOENT, "No such file or directory")
    else:
        # error_spec is a tuple ("other", errno_value)
        _, err_no = error_spec
        return OSError(err_no, f"OS error with errno {err_no}")


def _expected_error_type(error_spec):
    """Return the expected ErrorType for a given error specification."""
    if error_spec == "permission":
        return ErrorType.PERMISSION
    elif error_spec == "not_found":
        return ErrorType.NOT_FOUND
    else:
        return ErrorType.OTHER


@pytest.mark.property
class TestErrorClassificationCorrectnessProperty:
    """Property-based tests for error classification correctness.

    Property 14: For any OSError raised during file deletion, the classifier
    shall map PermissionError to PERMISSION, FileNotFoundError to NOT_FOUND,
    and all other OSError subtypes to OTHER, and the classification shall be
    deterministic (same exception type always maps to same error type).

    **Validates: Requirements 10.2**
    """

    @given(error_spec=_error_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_error_classification_maps_correctly(self, error_spec, tmp_path):
        """Any OSError raised during deletion is classified to the correct ErrorType."""
        # Create a real file so it passes the exists() check
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("content")

        exception = _make_exception(error_spec)
        expected_type = _expected_error_type(error_spec)

        with patch.object(Path, "unlink", side_effect=exception):
            result = clean_files([test_file], dry_run=False)

        assert len(result.errors) == 1
        assert result.errors[0].error_type == expected_type
        assert result.errors[0].path == test_file

    @given(error_spec=_error_strategy, num_calls=st.integers(min_value=2, max_value=5))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_error_classification_is_deterministic(self, error_spec, num_calls, tmp_path):
        """Same exception type always maps to the same error type (deterministic)."""
        exception = _make_exception(error_spec)
        classifications = []

        for i in range(num_calls):
            test_file = tmp_path / f"test_file_{i}.txt"
            test_file.write_text("content")

            with patch.object(Path, "unlink", side_effect=exception):
                result = clean_files([test_file], dry_run=False)

            assert len(result.errors) == 1
            classifications.append(result.errors[0].error_type)

        # All classifications should be identical for the same exception type
        assert all(c == classifications[0] for c in classifications), (
            f"Non-deterministic classification: got {classifications}"
        )
