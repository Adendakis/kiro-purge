"""Chat filter for Kiro Cleaner.

Filters chat files by content substring and date range using metadata timestamps.
All active filters are applied as a conjunction (all must match).
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from kiro_cleaner.chat_parser import ChatFile, ParseError, parse_chat_file


@dataclass
class ChatFilterCriteria:
    """Criteria for filtering chat files.

    Attributes:
        content: Case-insensitive substring to match in any message content.
        before: Include files with startTime < midnight UTC of this date.
        after: Include files with startTime > 23:59:59 UTC of this date.
    """

    content: str | None = None
    before: date | None = None
    after: date | None = None


def filter_chats(
    chat_files: list[Path],
    criteria: ChatFilterCriteria,
) -> list[Path]:
    """Apply filter criteria to chat files. Returns matching file paths.

    For each chat file:
    - Parses the file; skips on ParseError
    - Applies content filter (case-insensitive substring in any message)
    - Applies before filter (startTime < midnight UTC of the date)
    - Applies after filter (startTime > 23:59:59 UTC of the date)
    - All active filters must match (conjunction)
    - Files lacking startTime are skipped when date filters are active
    """
    matching: list[Path] = []

    for path in chat_files:
        result = parse_chat_file(path)

        # Skip files that can't be parsed
        if isinstance(result, ParseError):
            continue

        chat: ChatFile = result

        if not _matches_criteria(chat, criteria):
            continue

        matching.append(path)

    return matching


def _matches_criteria(chat: ChatFile, criteria: ChatFilterCriteria) -> bool:
    """Check if a parsed chat file matches all active filter criteria."""
    # Apply content filter
    if criteria.content is not None:
        if not _matches_content(chat, criteria.content):
            return False

    # Apply before filter
    if criteria.before is not None:
        if not _matches_before(chat, criteria.before):
            return False

    # Apply after filter
    if criteria.after is not None:
        if not _matches_after(chat, criteria.after):
            return False

    return True


def _matches_content(chat: ChatFile, search_term: str) -> bool:
    """Check if any message content contains the search term (case-insensitive)."""
    term_lower = search_term.lower()
    for message in chat.messages:
        if term_lower in message.content.lower():
            return True
    return False


def _matches_before(chat: ChatFile, before_date: date) -> bool:
    """Check if startTime < midnight UTC of the specified date.

    Returns False if startTime is None (skip files lacking startTime).
    startTime is in epoch milliseconds.
    """
    start_time = chat.metadata.start_time
    if start_time is None:
        return False

    # Convert startTime from milliseconds to seconds
    start_time_seconds = start_time / 1000.0

    # Midnight UTC of the specified date
    midnight_utc = datetime(
        before_date.year, before_date.month, before_date.day, tzinfo=timezone.utc
    ).timestamp()

    return start_time_seconds < midnight_utc


def _matches_after(chat: ChatFile, after_date: date) -> bool:
    """Check if startTime > 23:59:59 UTC of the specified date.

    Returns False if startTime is None (skip files lacking startTime).
    startTime is in epoch milliseconds.
    """
    start_time = chat.metadata.start_time
    if start_time is None:
        return False

    # Convert startTime from milliseconds to seconds
    start_time_seconds = start_time / 1000.0

    # 23:59:59 UTC of the specified date
    end_of_day_utc = datetime(
        after_date.year, after_date.month, after_date.day,
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    ).timestamp()

    return start_time_seconds > end_of_day_utc
