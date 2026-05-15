"""Cleaner engine for safe individual file deletion with error classification."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from kiro_cleaner.protection import is_protected


class ErrorType(Enum):
    """Classification of deletion errors."""

    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    OTHER = "other"


@dataclass
class DeletionError:
    """Represents an error encountered during file deletion."""

    path: Path
    error_type: ErrorType
    message: str


@dataclass
class CleanResult:
    """Summary of a cleaning operation."""

    deleted_count: int = 0
    deleted_bytes: int = 0
    errors: list[DeletionError] = field(default_factory=list)
    skipped_protected: list[Path] = field(default_factory=list)


def clean_files(
    files: list[Path],
    dry_run: bool = False,
) -> CleanResult:
    """Delete files individually with error handling and protection enforcement.

    For each file:
    1. Check is_protected() - if protected, add to skipped_protected and continue
    2. Check file exists - if not, log NOT_FOUND error and continue
    3. Get file size before deletion
    4. Try to delete (path.unlink())
    5. Classify any errors that occur

    In dry-run mode: perform steps 1-3 but skip actual deletion, still count
    files and bytes that would be deleted.

    Args:
        files: List of file paths to delete.
        dry_run: If True, report what would be deleted without deleting.

    Returns:
        CleanResult with counts, bytes, errors, and skipped protected files.
    """
    result = CleanResult()

    for file_path in files:
        # Step 1: Check protection
        protected, reason = is_protected(file_path)
        if protected:
            result.skipped_protected.append(file_path)
            continue

        # Step 2: Check file exists
        if not file_path.exists():
            result.errors.append(
                DeletionError(
                    path=file_path,
                    error_type=ErrorType.NOT_FOUND,
                    message="File no longer exists",
                )
            )
            continue

        # Step 3: Get file size before deletion
        try:
            file_size = file_path.stat().st_size
        except OSError:
            file_size = 0

        # Step 4: In dry-run mode, count but don't delete
        if dry_run:
            result.deleted_count += 1
            result.deleted_bytes += file_size
            continue

        # Step 5: Try to delete
        try:
            file_path.unlink()
            result.deleted_count += 1
            result.deleted_bytes += file_size
        except PermissionError as e:
            result.errors.append(
                DeletionError(
                    path=file_path,
                    error_type=ErrorType.PERMISSION,
                    message=str(e),
                )
            )
        except FileNotFoundError as e:
            result.errors.append(
                DeletionError(
                    path=file_path,
                    error_type=ErrorType.NOT_FOUND,
                    message=str(e),
                )
            )
        except OSError as e:
            result.errors.append(
                DeletionError(
                    path=file_path,
                    error_type=ErrorType.OTHER,
                    message=str(e),
                )
            )

    return result
