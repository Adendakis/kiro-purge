"""Property-based tests for the backup manager module."""

# Feature: kiro-cleaner-python, Property 9: Backup/restore round-trip

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from kiro_cleaner.backup import create_backup, restore_backup


# Strategy: generate a valid relative path segment (no path separators, no empty, filesystem-safe)
# Use only ASCII letters and digits to avoid case-insensitive filesystem collisions
# (e.g., macOS HFS+ treats 'Œ' and 'œ' as the same filename)
_path_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("Nd",),  # digits
        whitelist_characters="abcdefghijklmnopqrstuvwxyz_-",
    ),
    min_size=1,
    max_size=20,
)

# Strategy: generate a relative file path with 1-3 segments
_relative_path = st.lists(_path_segment, min_size=1, max_size=3).map(
    lambda parts: "/".join(parts)
)

# Strategy: generate file content as bytes
_file_content = st.binary(min_size=0, max_size=1024)


@st.composite
def file_set(draw):
    """Generate a set of (relative_path, content) pairs representing files in kiro_storage.

    Ensures unique paths (case-insensitive for macOS compatibility) and no path
    conflicts (a file path cannot also be a directory prefix for another file path).
    """
    num_files = draw(st.integers(min_value=1, max_value=10))
    paths_seen = set()
    paths_seen_lower = set()  # For case-insensitive dedup (macOS HFS+)
    files = []
    for _ in range(num_files):
        rel_path = draw(_relative_path)
        rel_path_lower = rel_path.lower()
        # Ensure uniqueness (case-insensitive)
        if rel_path_lower in paths_seen_lower:
            continue

        # Ensure no path conflicts: check that this path is not a prefix of
        # an existing path, and no existing path is a prefix of this one.
        has_conflict = False
        for existing in paths_seen_lower:
            if existing.startswith(rel_path_lower + "/") or rel_path_lower.startswith(existing + "/"):
                has_conflict = True
                break
        if has_conflict:
            continue

        paths_seen.add(rel_path)
        paths_seen_lower.add(rel_path_lower)
        content = draw(_file_content)
        files.append((rel_path, content))
    return files


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
@given(files_data=file_set())
def test_backup_restore_round_trip(tmp_path, files_data):
    """Property 9: For any set of files within Kiro_Storage, creating a backup
    archive and then restoring from that archive shall reproduce the original
    files at their original relative paths with identical content.

    **Validates: Requirements 5.1, 6.1**
    """
    # Skip if no files were generated (due to deduplication)
    assume(len(files_data) > 0)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        kiro_storage = td_path / "kiro_storage"
        kiro_storage.mkdir()
        backup_dir = td_path / "backups"
        backup_dir.mkdir()

        # Step 1: Create the files in mock kiro_storage
        original_files = []
        original_contents = {}
        for rel_path, content in files_data:
            file_path = kiro_storage / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            original_files.append(file_path)
            original_contents[rel_path] = content

        # Step 2: Create backup archive
        backup_result = create_backup(
            files=original_files,
            kiro_storage=kiro_storage,
            backup_dir=backup_dir,
        )

        assert backup_result.file_count == len(original_files)
        assert backup_result.archive_path.exists()

        # Step 3: Delete the original files
        for file_path in original_files:
            file_path.unlink()

        # Verify files are gone
        for file_path in original_files:
            assert not file_path.exists()

        # Step 4: Restore from backup with force=True
        restore_result = restore_backup(
            archive_path=backup_result.archive_path,
            kiro_storage=kiro_storage,
            force=True,
        )

        assert restore_result.restored_count == len(original_files)
        assert restore_result.errors == []

        # Step 5: Verify all files are restored at their original paths with identical content
        for rel_path, expected_content in original_contents.items():
            restored_path = kiro_storage / rel_path
            assert restored_path.exists(), (
                f"File not restored at expected path: {rel_path}"
            )
            actual_content = restored_path.read_bytes()
            assert actual_content == expected_content, (
                f"Content mismatch for {rel_path}: "
                f"expected {len(expected_content)} bytes, got {len(actual_content)} bytes"
            )
