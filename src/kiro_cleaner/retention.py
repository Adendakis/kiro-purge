"""Retention filter for Kiro Cleaner.

Filters files by retention period based on category and file modification time.
"""

import time
from pathlib import Path

DEFAULT_RETENTION: dict[str, int] = {
    "logs": 7,
    "crash_reports": 30,
    "history": 30,
    "chats": 30,
    "cache": 0,
    "temp": 0,
    "index": 0,
}

# Categories where retention=0 means always eligible for deletion
_ALWAYS_ELIGIBLE_CATEGORIES = {"cache", "temp", "index"}


def filter_by_retention(
    files: list[Path],
    category: str,
    keep_recent_days: int | None = None,
) -> list[Path]:
    """Filter files by retention period. Returns only files eligible for deletion.

    For cache, temp, and index categories: always returns ALL files regardless of age.
    For logs, crash_reports, history, chats: returns only files whose modification time
    is strictly older than the retention threshold.

    Args:
        files: List of file paths to filter.
        category: The category name (must be a key in DEFAULT_RETENTION).
        keep_recent_days: If provided, overrides the default retention period
            for logs, crash_reports, history, and chats categories.

    Returns:
        List of file paths eligible for deletion.
    """
    # For cache/temp/index: always return all files regardless of age
    if category in _ALWAYS_ELIGIBLE_CATEGORIES:
        return list(files)

    # Determine retention days
    if keep_recent_days is not None:
        retention_days = keep_recent_days
    else:
        retention_days = DEFAULT_RETENTION.get(category, 0)

    # Calculate the threshold timestamp
    now = time.time()
    threshold_seconds = retention_days * 86400
    cutoff_time = now - threshold_seconds

    # Filter to files strictly older than the retention threshold
    eligible: list[Path] = []
    for file_path in files:
        try:
            mtime = file_path.stat().st_mtime
            if mtime < cutoff_time:
                eligible.append(file_path)
        except OSError:
            # If we can't stat the file, skip it
            continue

    return eligible
