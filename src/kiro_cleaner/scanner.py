"""Storage scanner for Kiro Cleaner - analyses disk usage by category."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CategoryResult:
    """Result for a single scan category."""

    name: str
    file_count: int
    total_bytes: int
    files: list[Path]


@dataclass
class ScanResult:
    """Complete scan result across all categories."""

    categories: dict[str, CategoryResult]
    uncategorized: CategoryResult
    total_bytes: int
    total_files: int
    warnings: list[str]


# Category directory mappings (relative to kiro_storage root)
_CATEGORY_DIRS: dict[str, list[str]] = {
    "logs": ["logs"],
    "cache": ["Cache", "CachedData", "GPUCache"],
    "history": ["User/History"],
    "crash_reports": ["Crashpad"],
}

# Special path-based categories
_CHATS_PREFIX = "User/globalStorage/kiro.kiroagent"
_CHATS_EXTENSION = ".chat"
_INDEX_PREFIX = "User/globalStorage/kiro.kiroagent/index"

# Temp file extensions
_TEMP_EXTENSIONS = {".tmp", ".temp"}


def _classify_file(relative_path: Path) -> str:
    """Classify a file into a category based on its relative path.

    Priority: directory-based categories first, then temp by extension, then uncategorized.

    Args:
        relative_path: Path relative to kiro_storage root.

    Returns:
        Category name string.
    """
    # Convert to posix string for consistent path matching
    rel_str = relative_path.as_posix()
    parts = relative_path.parts

    if not parts:
        return "uncategorized"

    # Check index first (more specific than chats)
    if rel_str.startswith(_INDEX_PREFIX + "/") or rel_str == _INDEX_PREFIX:
        return "index"

    # Check chats (files matching User/globalStorage/kiro.kiroagent/**/*.chat)
    if (
        rel_str.startswith(_CHATS_PREFIX + "/")
        and relative_path.suffix == _CHATS_EXTENSION
    ):
        return "chats"

    # Check directory-based categories
    for category, dirs in _CATEGORY_DIRS.items():
        for dir_prefix in dirs:
            if rel_str.startswith(dir_prefix + "/") or rel_str == dir_prefix:
                return category

    # Check temp extensions for files not already categorized
    if relative_path.suffix.lower() in _TEMP_EXTENSIONS:
        return "temp"

    return "uncategorized"


def scan_storage(kiro_storage: Path) -> ScanResult:
    """Traverse Kiro storage and calculate usage per category.

    Walks the entire directory tree, classifying each file into exactly one
    category. Files that don't match any category go to uncategorized.
    Permission errors are captured as warnings rather than stopping the scan.

    Args:
        kiro_storage: Path to the Kiro storage root directory.

    Returns:
        ScanResult with categorized file information.
    """
    # Initialize category buckets
    category_names = ["logs", "cache", "chats", "index", "temp", "history", "crash_reports"]
    categories: dict[str, list[Path]] = {name: [] for name in category_names}
    category_bytes: dict[str, int] = {name: 0 for name in category_names}
    uncategorized_files: list[Path] = []
    scan_warnings: list[str] = []

    # Mutable container for uncategorized byte tracking
    uncategorized_bytes_ref: list[int] = [0]

    # Walk the directory tree
    _walk_directory(
        kiro_storage,
        kiro_storage,
        categories,
        category_bytes,
        uncategorized_files,
        uncategorized_bytes_ref,
        scan_warnings,
    )

    # Build CategoryResult objects
    uncategorized_bytes_total = uncategorized_bytes_ref[0]

    result_categories: dict[str, CategoryResult] = {}
    for name in category_names:
        result_categories[name] = CategoryResult(
            name=name,
            file_count=len(categories[name]),
            total_bytes=category_bytes[name],
            files=categories[name],
        )

    uncategorized_result = CategoryResult(
        name="uncategorized",
        file_count=len(uncategorized_files),
        total_bytes=uncategorized_bytes_total,
        files=uncategorized_files,
    )

    total_bytes = sum(category_bytes.values()) + uncategorized_bytes_total
    total_files = sum(len(files) for files in categories.values()) + len(uncategorized_files)

    return ScanResult(
        categories=result_categories,
        uncategorized=uncategorized_result,
        total_bytes=total_bytes,
        total_files=total_files,
        warnings=scan_warnings,
    )


def _walk_directory(
    current_dir: Path,
    root: Path,
    categories: dict[str, list[Path]],
    category_bytes: dict[str, int],
    uncategorized_files: list[Path],
    uncategorized_bytes_ref: list[int],
    scan_warnings: list[str],
) -> None:
    """Recursively walk a directory, classifying files into categories.

    Args:
        current_dir: Directory currently being scanned.
        root: The kiro_storage root for computing relative paths.
        categories: Dict mapping category names to file lists.
        category_bytes: Dict mapping category names to byte totals.
        uncategorized_files: List collecting uncategorized files.
        uncategorized_bytes_ref: Single-element list for mutable uncategorized byte count.
        scan_warnings: List collecting warning messages.
    """
    try:
        entries = list(os.scandir(current_dir))
    except PermissionError as e:
        scan_warnings.append(f"Permission denied: {current_dir}")
        return
    except OSError as e:
        scan_warnings.append(f"Error accessing {current_dir}: {e}")
        return

    for entry in entries:
        entry_path = Path(entry.path)

        if entry.is_dir(follow_symlinks=False):
            _walk_directory(
                entry_path,
                root,
                categories,
                category_bytes,
                uncategorized_files,
                uncategorized_bytes_ref,
                scan_warnings,
            )
        elif entry.is_file(follow_symlinks=False):
            try:
                file_size = entry.stat(follow_symlinks=False).st_size
            except PermissionError:
                scan_warnings.append(f"Permission denied: {entry_path}")
                continue
            except OSError as e:
                scan_warnings.append(f"Error reading {entry_path}: {e}")
                continue

            relative_path = entry_path.relative_to(root)
            category = _classify_file(relative_path)

            if category == "uncategorized":
                uncategorized_files.append(entry_path)
                uncategorized_bytes_ref[0] += file_size
            else:
                categories[category].append(entry_path)
                category_bytes[category] += file_size



def format_size(bytes_count: int) -> str:
    """Format bytes as human-readable string using the largest appropriate unit.

    Uses the largest unit (B, KB, MB, GB) where the numeric value is >= 1.

    Args:
        bytes_count: Non-negative integer byte count.

    Returns:
        Formatted string like "1.5 MB", "256 KB", "42 B".
    """
    if bytes_count < 0:
        bytes_count = 0

    units = [
        ("GB", 1024**3),
        ("MB", 1024**2),
        ("KB", 1024),
        ("B", 1),
    ]

    for unit_name, unit_size in units:
        if bytes_count >= unit_size:
            value = bytes_count / unit_size
            # Use integer display if value is whole, otherwise 2 decimal places
            if value == int(value):
                return f"{int(value)} {unit_name}"
            else:
                # Format with up to 2 decimal places, strip trailing zeros
                formatted = f"{value:.2f}".rstrip("0").rstrip(".")
                return f"{formatted} {unit_name}"

    # 0 bytes
    return "0 B"
