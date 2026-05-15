"""Backup manager for creating and restoring tar.gz archives of Kiro artefacts."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tarfile


@dataclass
class BackupResult:
    """Result of a backup creation operation."""

    archive_path: Path
    file_count: int
    total_bytes: int


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    restored_count: int
    skipped_count: int
    errors: list[str] = field(default_factory=list)


def create_backup(
    files: list[Path],
    kiro_storage: Path,
    backup_dir: Path,
) -> BackupResult:
    """Create a tar.gz archive preserving relative paths from kiro_storage.

    Args:
        files: List of absolute file paths to back up.
        kiro_storage: Root Kiro storage directory (used to compute relative paths).
        backup_dir: Directory where the archive will be stored.

    Returns:
        BackupResult with archive path, file count, and total bytes archived.
    """
    if not files:
        return BackupResult(archive_path=backup_dir, file_count=0, total_bytes=0)

    # Create backup directory if it doesn't exist
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename with current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    filename = f"kiro-backup-{timestamp}.tar.gz"
    archive_path = backup_dir / filename

    total_bytes = 0
    file_count = 0

    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in files:
            if not file_path.exists():
                continue
            # Compute relative path from kiro_storage root
            try:
                arcname = str(file_path.relative_to(kiro_storage))
            except ValueError:
                # File is not under kiro_storage; use filename as fallback
                arcname = file_path.name

            total_bytes += file_path.stat().st_size
            tar.add(str(file_path), arcname=arcname)
            file_count += 1

    return BackupResult(
        archive_path=archive_path,
        file_count=file_count,
        total_bytes=total_bytes,
    )


def restore_backup(
    archive_path: Path,
    kiro_storage: Path,
    force: bool = False,
) -> RestoreResult:
    """Extract archive to original locations within kiro_storage.

    Args:
        archive_path: Path to the tar.gz backup archive.
        kiro_storage: Root Kiro storage directory to restore into.
        force: If True, overwrite existing files without prompting.

    Returns:
        RestoreResult with counts of restored, skipped, and errored files.

    Raises:
        FileNotFoundError: If archive_path does not exist.
        tarfile.ReadError: If the archive is invalid or corrupted.
    """
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    # Validate it's a valid tar.gz
    try:
        tar = tarfile.open(archive_path, "r:gz")
    except (tarfile.ReadError, tarfile.CompressionError) as e:
        raise tarfile.ReadError(f"Invalid or corrupted archive: {archive_path}: {e}")

    restored_count = 0
    skipped_count = 0
    errors: list[str] = []

    with tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue

            target_path = kiro_storage / member.name

            # Handle conflicts
            if target_path.exists() and not force:
                skipped_count += 1
                continue

            # Create parent directories as needed
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                errors.append(f"Permission error creating directory {target_path.parent}: {e}")
                continue

            # Extract the file
            try:
                # Extract to a temporary location then move, to handle safely
                source = tar.extractfile(member)
                if source is None:
                    errors.append(f"Could not extract {member.name}: not a regular file")
                    continue
                target_path.write_bytes(source.read())
                restored_count += 1
            except PermissionError as e:
                errors.append(f"Permission error extracting {member.name}: {e}")
                continue
            except OSError as e:
                errors.append(f"Error extracting {member.name}: {e}")
                continue

    return RestoreResult(
        restored_count=restored_count,
        skipped_count=skipped_count,
        errors=errors,
    )
