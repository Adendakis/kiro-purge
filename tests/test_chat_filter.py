"""Unit tests for chat_filter module."""

import json
from datetime import date
from pathlib import Path

import pytest

from kiro_cleaner.chat_filter import ChatFilterCriteria, filter_chats


def _make_chat_file(tmp_path: Path, name: str, messages: list[dict], start_time: int | None = None) -> Path:
    """Helper to create a chat file with given messages and optional startTime."""
    metadata = {
        "modelId": "test-model",
        "modelProvider": "test-provider",
        "workflow": "test-workflow",
    }
    if start_time is not None:
        metadata["startTime"] = start_time
    data = {"chat": messages, "metadata": metadata}
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


class TestChatFilterCriteria:
    """Tests for ChatFilterCriteria dataclass."""

    def test_defaults_are_none(self):
        criteria = ChatFilterCriteria()
        assert criteria.content is None
        assert criteria.before is None
        assert criteria.after is None

    def test_fields_set(self):
        criteria = ChatFilterCriteria(
            content="hello",
            before=date(2024, 1, 15),
            after=date(2024, 1, 1),
        )
        assert criteria.content == "hello"
        assert criteria.before == date(2024, 1, 15)
        assert criteria.after == date(2024, 1, 1)


class TestContentFilter:
    """Tests for content-based filtering."""

    def test_matches_case_insensitive(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello World"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(content="hello world")
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_matches_substring(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "I need help with Python sorting"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(content="python")
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_no_match(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello World"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(content="goodbye")
        result = filter_chats([path], criteria)
        assert result == []

    def test_matches_in_any_message(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [
                {"role": "human", "content": "What is Python?"},
                {"role": "bot", "content": "Python is a programming language"},
            ],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(content="programming language")
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_empty_content_matches_all(self, tmp_path):
        """Empty string content filter matches all files (substring of everything)."""
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(content="")
        result = filter_chats([path], criteria)
        assert result == [path]


class TestBeforeFilter:
    """Tests for before-date filtering."""

    def test_file_before_date(self, tmp_path):
        # startTime: 2023-11-14 (epoch ms for a date well before 2024-01-01)
        # 1700000000000 ms = 2023-11-14T22:13:20 UTC
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(before=date(2024, 1, 1))
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_file_not_before_date(self, tmp_path):
        # startTime: 2023-11-14 UTC - not before 2023-01-01
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(before=date(2023, 1, 1))
        result = filter_chats([path], criteria)
        assert result == []

    def test_skip_file_without_start_time(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=None,
        )
        criteria = ChatFilterCriteria(before=date(2025, 1, 1))
        result = filter_chats([path], criteria)
        assert result == []


class TestAfterFilter:
    """Tests for after-date filtering."""

    def test_file_after_date(self, tmp_path):
        # startTime: 2023-11-14T22:13:20 UTC - after 2023-01-01
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(after=date(2023, 1, 1))
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_file_not_after_date(self, tmp_path):
        # startTime: 2023-11-14 UTC - not after 2024-01-01
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(after=date(2024, 1, 1))
        result = filter_chats([path], criteria)
        assert result == []

    def test_skip_file_without_start_time(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=None,
        )
        criteria = ChatFilterCriteria(after=date(2020, 1, 1))
        result = filter_chats([path], criteria)
        assert result == []


class TestConjunction:
    """Tests for conjunction of multiple filters."""

    def test_content_and_before(self, tmp_path):
        # Matches content but not before date
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello World"}],
            start_time=1700000000000,  # 2023-11-14
        )
        criteria = ChatFilterCriteria(content="hello", before=date(2023, 1, 1))
        result = filter_chats([path], criteria)
        assert result == []

    def test_all_filters_match(self, tmp_path):
        # 1700000000000 ms = 2023-11-14T22:13:20 UTC
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello World"}],
            start_time=1700000000000,
        )
        criteria = ChatFilterCriteria(
            content="hello",
            before=date(2024, 1, 1),
            after=date(2023, 1, 1),
        )
        result = filter_chats([path], criteria)
        assert result == [path]

    def test_content_matches_but_date_fails(self, tmp_path):
        path = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello World"}],
            start_time=1700000000000,  # 2023-11-14
        )
        # Content matches, after matches, but before fails
        criteria = ChatFilterCriteria(
            content="hello",
            before=date(2023, 11, 14),  # midnight of same day - startTime is at 22:13, not before midnight
            after=date(2023, 1, 1),
        )
        result = filter_chats([path], criteria)
        assert result == []


class TestParseErrorHandling:
    """Tests for handling unparseable files."""

    def test_skip_malformed_json(self, tmp_path):
        path = tmp_path / "bad.chat"
        path.write_text("not json at all")
        criteria = ChatFilterCriteria(content="hello")
        result = filter_chats([path], criteria)
        assert result == []

    def test_skip_missing_metadata(self, tmp_path):
        path = tmp_path / "bad.chat"
        path.write_text(json.dumps({"chat": [{"role": "human", "content": "hi"}]}))
        criteria = ChatFilterCriteria(content="hi")
        result = filter_chats([path], criteria)
        assert result == []

    def test_mixed_valid_and_invalid(self, tmp_path):
        good = _make_chat_file(
            tmp_path, "good.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        bad = tmp_path / "bad.chat"
        bad.write_text("invalid json")
        criteria = ChatFilterCriteria(content="hello")
        result = filter_chats([good, bad], criteria)
        assert result == [good]


class TestNoFilters:
    """Tests for when no filters are active (all criteria are None)."""

    def test_no_criteria_returns_all_parseable(self, tmp_path):
        path1 = _make_chat_file(
            tmp_path, "chat1.chat",
            [{"role": "human", "content": "Hello"}],
            start_time=1700000000000,
        )
        path2 = _make_chat_file(
            tmp_path, "chat2.chat",
            [{"role": "bot", "content": "World"}],
            start_time=1700100000000,
        )
        criteria = ChatFilterCriteria()
        result = filter_chats([path1, path2], criteria)
        assert result == [path1, path2]

    def test_empty_file_list(self):
        criteria = ChatFilterCriteria(content="hello")
        result = filter_chats([], criteria)
        assert result == []


# Feature: kiro-cleaner-python, Property 11: Chat content filter correctness
import json as _json
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Strategy for generating valid chat messages
_chat_message_st = st.fixed_dictionaries({
    "role": st.sampled_from(["human", "bot", "tool"]),
    "content": st.text(min_size=0, max_size=200),
})

# Strategy for generating valid chat metadata
_chat_metadata_st = st.fixed_dictionaries({
    "modelId": st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P"))),
    "modelProvider": st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P"))),
    "workflow": st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P"))),
    "startTime": st.integers(min_value=0, max_value=2000000000000),
})

# Strategy for generating a valid chat file structure
_chat_file_st = st.fixed_dictionaries({
    "chat": st.lists(_chat_message_st, min_size=1, max_size=10),
    "metadata": _chat_metadata_st,
})

# Strategy for search terms - use printable text to avoid null bytes
_search_term_st = st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P", "Z")))


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(chat_data=_chat_file_st, search_term=_search_term_st)
def test_property_chat_content_filter_correctness(tmp_path_factory, chat_data, search_term):
    """Property 11: Chat content filter correctness.

    For any Chat_File and for any search term, the content filter shall include
    the file in results if and only if at least one message content field contains
    the search term as a case-insensitive substring match.

    **Validates: Requirements 7.1**
    """
    # Create a temporary directory for this test instance
    tmp_path = tmp_path_factory.mktemp("chat_filter")

    # Write the chat file to disk
    chat_path = tmp_path / "test.chat"
    chat_path.write_text(_json.dumps(chat_data))

    # Apply the content filter
    criteria = ChatFilterCriteria(content=search_term)
    result = filter_chats([chat_path], criteria)

    # Compute expected result: file should be included iff any message content
    # contains the search term as a case-insensitive substring
    term_lower = search_term.lower()
    expected_match = any(
        term_lower in msg["content"].lower()
        for msg in chat_data["chat"]
    )

    if expected_match:
        assert result == [chat_path], (
            f"Expected file to be included (search_term={search_term!r} found in messages) "
            f"but filter returned empty list"
        )
    else:
        assert result == [], (
            f"Expected file to be excluded (search_term={search_term!r} not found in messages) "
            f"but filter returned the file"
        )


# Feature: kiro-cleaner-python, Property 12: Chat date filter correctness
import tempfile
from datetime import datetime, timezone

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


@st.composite
def chat_file_with_start_time(draw):
    """Strategy to generate a chat file dict with a numeric startTime."""
    role = draw(st.sampled_from(["human", "bot", "tool"]))
    content = draw(st.text(min_size=1, max_size=100))
    # startTime in epoch milliseconds: range from year ~1970 to ~2060
    start_time = draw(st.integers(min_value=0, max_value=2_000_000_000_000))
    data = {
        "chat": [{"role": role, "content": content}],
        "metadata": {
            "modelId": "test-model",
            "modelProvider": "test-provider",
            "workflow": "test-workflow",
            "startTime": start_time,
        },
    }
    return data, start_time


@st.composite
def date_boundary(draw):
    """Strategy to generate a valid date boundary."""
    # Generate dates between 1971-01-01 and 2060-12-31
    d = draw(st.dates(
        min_value=date(1971, 1, 1),
        max_value=date(2060, 12, 31),
    ))
    return d


@pytest.mark.property
class TestChatDateFilterProperty:
    """Property 12: Chat date filter correctness.

    **Validates: Requirements 7.2, 7.3, 7.8**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        chat_data=chat_file_with_start_time(),
        boundary=date_boundary(),
    )
    def test_before_filter_correctness(self, chat_data, boundary, tmp_path):
        """Before-filter includes file iff startTime < midnight UTC of the date."""
        data, start_time_ms = chat_data

        # Write chat file to disk using a unique name per example
        chat_path = tmp_path / f"test_{start_time_ms}_{boundary.isoformat()}.chat"
        chat_path.write_text(json.dumps(data))

        # Apply before filter
        criteria = ChatFilterCriteria(before=boundary)
        result = filter_chats([chat_path], criteria)

        # Compute expected: startTime (ms) < midnight UTC of boundary date
        midnight_utc = datetime(
            boundary.year, boundary.month, boundary.day, tzinfo=timezone.utc
        ).timestamp()
        start_time_seconds = start_time_ms / 1000.0

        if start_time_seconds < midnight_utc:
            assert result == [chat_path], (
                f"Expected file included: startTime={start_time_ms}ms "
                f"({start_time_seconds}s) < midnight={midnight_utc}s of {boundary}"
            )
        else:
            assert result == [], (
                f"Expected file excluded: startTime={start_time_ms}ms "
                f"({start_time_seconds}s) >= midnight={midnight_utc}s of {boundary}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        chat_data=chat_file_with_start_time(),
        boundary=date_boundary(),
    )
    def test_after_filter_correctness(self, chat_data, boundary, tmp_path):
        """After-filter includes file iff startTime > 23:59:59 UTC of the date."""
        data, start_time_ms = chat_data

        # Write chat file to disk using a unique name per example
        chat_path = tmp_path / f"test_{start_time_ms}_{boundary.isoformat()}.chat"
        chat_path.write_text(json.dumps(data))

        # Apply after filter
        criteria = ChatFilterCriteria(after=boundary)
        result = filter_chats([chat_path], criteria)

        # Compute expected: startTime (ms) > 23:59:59 UTC of boundary date
        end_of_day_utc = datetime(
            boundary.year, boundary.month, boundary.day,
            hour=23, minute=59, second=59, tzinfo=timezone.utc,
        ).timestamp()
        start_time_seconds = start_time_ms / 1000.0

        if start_time_seconds > end_of_day_utc:
            assert result == [chat_path], (
                f"Expected file included: startTime={start_time_ms}ms "
                f"({start_time_seconds}s) > end_of_day={end_of_day_utc}s of {boundary}"
            )
        else:
            assert result == [], (
                f"Expected file excluded: startTime={start_time_ms}ms "
                f"({start_time_seconds}s) <= end_of_day={end_of_day_utc}s of {boundary}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(boundary=date_boundary())
    def test_missing_start_time_excluded_from_before_filter(self, boundary, tmp_path):
        """Files lacking startTime are excluded from before-filter results."""
        data = {
            "chat": [{"role": "human", "content": "hello"}],
            "metadata": {
                "modelId": "test-model",
                "modelProvider": "test-provider",
                "workflow": "test-workflow",
            },
        }
        chat_path = tmp_path / f"no_time_{boundary.isoformat()}.chat"
        chat_path.write_text(json.dumps(data))

        criteria = ChatFilterCriteria(before=boundary)
        result = filter_chats([chat_path], criteria)
        assert result == [], (
            f"File without startTime should be excluded from before-filter with date={boundary}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(boundary=date_boundary())
    def test_missing_start_time_excluded_from_after_filter(self, boundary, tmp_path):
        """Files lacking startTime are excluded from after-filter results."""
        data = {
            "chat": [{"role": "human", "content": "hello"}],
            "metadata": {
                "modelId": "test-model",
                "modelProvider": "test-provider",
                "workflow": "test-workflow",
            },
        }
        chat_path = tmp_path / f"no_time_{boundary.isoformat()}.chat"
        chat_path.write_text(json.dumps(data))

        criteria = ChatFilterCriteria(after=boundary)
        result = filter_chats([chat_path], criteria)
        assert result == [], (
            f"File without startTime should be excluded from after-filter with date={boundary}"
        )


# Feature: kiro-cleaner-python, Property 13: Chat filter conjunction
import string

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


def _chat_file_strategy():
    """Strategy to generate chat file data with random content and startTime."""
    return st.fixed_dictionaries({
        "content": st.text(alphabet=string.ascii_letters + string.digits + " ", min_size=1, max_size=50),
        "start_time": st.one_of(
            st.none(),
            st.integers(min_value=946684800000, max_value=1893456000000),  # 2000-01-01 to 2030-01-01 in ms
        ),
    })


def _filter_criteria_strategy():
    """Strategy to generate random filter criteria (some may be None)."""
    return st.fixed_dictionaries({
        "content": st.one_of(
            st.none(),
            st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=10),
        ),
        "before": st.one_of(
            st.none(),
            st.dates(
                min_value=date(2000, 1, 1),
                max_value=date(2030, 1, 1),
            ),
        ),
        "after": st.one_of(
            st.none(),
            st.dates(
                min_value=date(2000, 1, 1),
                max_value=date(2030, 1, 1),
            ),
        ),
    })


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    chat_files_data=st.lists(_chat_file_strategy(), min_size=1, max_size=10),
    criteria_data=_filter_criteria_strategy(),
)
def test_chat_filter_conjunction(tmp_path_factory, chat_files_data, criteria_data):
    """Property 13: Chat filter conjunction.

    For any set of chat filter criteria (content, before-date, after-date) applied
    simultaneously, the resulting set of matching files shall equal the intersection
    of the sets that would be returned by applying each filter individually.

    **Validates: Requirements 7.4**
    """
    tmp_path = tmp_path_factory.mktemp("chats")

    # Create chat files on disk
    paths = []
    for i, file_data in enumerate(chat_files_data):
        metadata = {
            "modelId": "test-model",
            "modelProvider": "test-provider",
            "workflow": "test-workflow",
        }
        if file_data["start_time"] is not None:
            metadata["startTime"] = file_data["start_time"]

        data = {
            "chat": [{"role": "human", "content": file_data["content"]}],
            "metadata": metadata,
        }
        path = tmp_path / f"chat_{i}.chat"
        path.write_text(json.dumps(data))
        paths.append(path)

    # Build the combined criteria
    combined_criteria = ChatFilterCriteria(
        content=criteria_data["content"],
        before=criteria_data["before"],
        after=criteria_data["after"],
    )

    # Apply combined filter
    combined_result = set(filter_chats(paths, combined_criteria))

    # Apply each individual filter separately and compute intersection
    active_filters = []

    if criteria_data["content"] is not None:
        content_only = ChatFilterCriteria(content=criteria_data["content"])
        active_filters.append(set(filter_chats(paths, content_only)))

    if criteria_data["before"] is not None:
        before_only = ChatFilterCriteria(before=criteria_data["before"])
        active_filters.append(set(filter_chats(paths, before_only)))

    if criteria_data["after"] is not None:
        after_only = ChatFilterCriteria(after=criteria_data["after"])
        active_filters.append(set(filter_chats(paths, after_only)))

    # Compute intersection of all individual filter results
    if active_filters:
        expected = active_filters[0]
        for filter_result in active_filters[1:]:
            expected = expected & filter_result
    else:
        # No active filters means all parseable files match
        no_filter_criteria = ChatFilterCriteria()
        expected = set(filter_chats(paths, no_filter_criteria))

    assert combined_result == expected
