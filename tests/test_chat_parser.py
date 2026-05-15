"""Tests for the chat parser module."""

import json
from pathlib import Path

import pytest

from kiro_cleaner.chat_parser import (
    ChatFile,
    ChatMessage,
    ChatMetadata,
    ParseError,
    VALID_ROLES,
    parse_chat_file,
    pretty_print_chat,
)


class TestParseValidChatFile:
    """Tests for parsing valid chat files."""

    def test_parse_valid_chat_file(self, mock_chat_file):
        """Parse a valid chat file and verify all fields."""
        result = parse_chat_file(mock_chat_file)

        assert isinstance(result, ChatFile)
        assert len(result.messages) == 2
        assert result.messages[0].role == "human"
        assert result.messages[0].content == "Test message"
        assert result.messages[1].role == "bot"
        assert result.messages[1].content == "Test response"
        assert result.metadata.model_id == "test-model"
        assert result.metadata.model_provider == "test-provider"
        assert result.metadata.workflow == "test-workflow"
        assert result.metadata.start_time == 1700000000000
        assert result.metadata.end_time == 1700000060000

    def test_parse_chat_with_tool_role(self, tmp_path):
        """Parse a chat file containing a tool message."""
        data = {
            "chat": [
                {"role": "human", "content": "Run this code"},
                {"role": "tool", "content": "Output: success"},
                {"role": "bot", "content": "The code ran successfully."},
            ],
            "metadata": {
                "modelId": "model-1",
                "modelProvider": "provider-1",
                "workflow": "code",
            },
        }
        path = tmp_path / "tool.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ChatFile)
        assert len(result.messages) == 3
        assert result.messages[1].role == "tool"

    def test_parse_chat_without_optional_times(self, tmp_path):
        """Parse a chat file without startTime and endTime."""
        data = {
            "chat": [{"role": "human", "content": "Hello"}],
            "metadata": {
                "modelId": "m",
                "modelProvider": "p",
                "workflow": "w",
            },
        }
        path = tmp_path / "no_times.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ChatFile)
        assert result.metadata.start_time is None
        assert result.metadata.end_time is None

    def test_raw_data_preserves_original(self, tmp_path):
        """raw_data should preserve all original fields including extra ones."""
        data = {
            "chat": [{"role": "human", "content": "Hi"}],
            "metadata": {
                "modelId": "m",
                "modelProvider": "p",
                "workflow": "w",
                "extraField": "extra_value",
            },
            "customTopLevel": True,
        }
        path = tmp_path / "extra.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ChatFile)
        assert result.raw_data == data
        assert result.raw_data["customTopLevel"] is True
        assert result.raw_data["metadata"]["extraField"] == "extra_value"


class TestParseErrors:
    """Tests for parse error conditions."""

    def test_malformed_json(self, tmp_path):
        """Return ParseError for malformed JSON."""
        path = tmp_path / "bad.chat"
        path.write_text("not valid json {{{")

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert result.path == path
        assert "Malformed JSON" in result.reason

    def test_missing_chat_field(self, tmp_path):
        """Return ParseError when 'chat' field is missing."""
        data = {"metadata": {"modelId": "m", "modelProvider": "p", "workflow": "w"}}
        path = tmp_path / "no_chat.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert '"chat"' in result.reason

    def test_chat_not_array(self, tmp_path):
        """Return ParseError when 'chat' is not an array."""
        data = {
            "chat": "not an array",
            "metadata": {"modelId": "m", "modelProvider": "p", "workflow": "w"},
        }
        path = tmp_path / "chat_str.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "must be an array" in result.reason

    def test_missing_metadata_field(self, tmp_path):
        """Return ParseError when 'metadata' field is missing."""
        data = {"chat": [{"role": "human", "content": "Hi"}]}
        path = tmp_path / "no_meta.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert '"metadata"' in result.reason

    def test_metadata_not_object(self, tmp_path):
        """Return ParseError when 'metadata' is not an object."""
        data = {
            "chat": [{"role": "human", "content": "Hi"}],
            "metadata": "string",
        }
        path = tmp_path / "meta_str.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "must be an object" in result.reason

    def test_metadata_missing_required_fields(self, tmp_path):
        """Return ParseError when metadata is missing required fields."""
        data = {
            "chat": [{"role": "human", "content": "Hi"}],
            "metadata": {"modelId": "m"},
        }
        path = tmp_path / "meta_incomplete.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "modelProvider" in result.reason

    def test_invalid_role(self, tmp_path):
        """Return ParseError for invalid role value."""
        data = {
            "chat": [{"role": "invalid_role", "content": "Hi"}],
            "metadata": {"modelId": "m", "modelProvider": "p", "workflow": "w"},
        }
        path = tmp_path / "bad_role.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "invalid role" in result.reason
        assert "invalid_role" in result.reason

    def test_message_missing_role(self, tmp_path):
        """Return ParseError when a message is missing 'role'."""
        data = {
            "chat": [{"content": "Hi"}],
            "metadata": {"modelId": "m", "modelProvider": "p", "workflow": "w"},
        }
        path = tmp_path / "no_role.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "role" in result.reason

    def test_message_missing_content(self, tmp_path):
        """Return ParseError when a message is missing 'content'."""
        data = {
            "chat": [{"role": "human"}],
            "metadata": {"modelId": "m", "modelProvider": "p", "workflow": "w"},
        }
        path = tmp_path / "no_content.chat"
        path.write_text(json.dumps(data))

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "content" in result.reason

    def test_nonexistent_file(self, tmp_path):
        """Return ParseError for a file that doesn't exist."""
        path = tmp_path / "nonexistent.chat"

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "Cannot read file" in result.reason

    def test_top_level_not_object(self, tmp_path):
        """Return ParseError when top-level JSON is not an object."""
        path = tmp_path / "array.chat"
        path.write_text("[1, 2, 3]")

        result = parse_chat_file(path)
        assert isinstance(result, ParseError)
        assert "must be an object" in result.reason


class TestPrettyPrintChat:
    """Tests for pretty_print_chat function."""

    def test_pretty_print_produces_valid_json(self, mock_chat_file):
        """pretty_print_chat should produce valid JSON."""
        chat = parse_chat_file(mock_chat_file)
        assert isinstance(chat, ChatFile)

        output = pretty_print_chat(chat)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_round_trip_preserves_data(self, mock_chat_file):
        """Parse → pretty_print → parse should yield equal objects."""
        chat1 = parse_chat_file(mock_chat_file)
        assert isinstance(chat1, ChatFile)

        json_str = pretty_print_chat(chat1)

        # Write back and re-parse
        mock_chat_file.write_text(json_str)
        chat2 = parse_chat_file(mock_chat_file)
        assert isinstance(chat2, ChatFile)

        assert chat1.messages == chat2.messages
        assert chat1.metadata == chat2.metadata
        assert chat1.raw_data == chat2.raw_data

    def test_pretty_print_uses_indent(self, mock_chat_file):
        """pretty_print_chat should use indent=2 for readability."""
        chat = parse_chat_file(mock_chat_file)
        assert isinstance(chat, ChatFile)

        output = pretty_print_chat(chat)
        # Indented JSON has newlines and spaces
        assert "\n" in output
        assert "  " in output


class TestValidRoles:
    """Tests for VALID_ROLES constant."""

    def test_valid_roles_contains_expected(self):
        """VALID_ROLES should contain human, bot, and tool."""
        assert VALID_ROLES == {"human", "bot", "tool"}


# Feature: kiro-cleaner-python, Property 1: Chat parse/print round-trip

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Hypothesis strategies for generating valid chat file structures
chat_message_st = st.fixed_dictionaries({
    "role": st.sampled_from(["human", "bot", "tool"]),
    "content": st.text(min_size=0, max_size=500),
})

chat_metadata_st = st.fixed_dictionaries({
    "modelId": st.text(min_size=1, max_size=50),
    "modelProvider": st.text(min_size=1, max_size=50),
    "workflow": st.text(min_size=1, max_size=50),
}, optional={
    "startTime": st.integers(min_value=0, max_value=2000000000000),
    "endTime": st.integers(min_value=0, max_value=2000000000000),
})

chat_file_st = st.fixed_dictionaries({
    "chat": st.lists(chat_message_st, min_size=1, max_size=20),
    "metadata": chat_metadata_st,
})


class TestChatParseRoundTrip:
    """Property-based test for chat parse/print round-trip.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """

    @pytest.mark.property
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(chat_data=chat_file_st)
    def test_parse_print_round_trip(self, chat_data, tmp_path):
        """For any valid Chat_File JSON structure, parsing into a ChatFile object
        and then pretty-printing back to JSON and re-parsing should yield a deeply
        equal object (identical keys, values, and array ordering).
        """
        import uuid

        unique_id = uuid.uuid4().hex

        # Step 1: Write generated chat data to a temp file
        file_path = tmp_path / f"generated_{unique_id}.chat"
        file_path.write_text(json.dumps(chat_data))

        # Step 2: Parse with parse_chat_file
        result1 = parse_chat_file(file_path)
        assert isinstance(result1, ChatFile), f"Expected ChatFile, got ParseError: {result1}"

        # Step 3: Pretty-print with pretty_print_chat
        printed_json = pretty_print_chat(result1)

        # Step 4: Write the pretty-printed output to a file
        round_trip_path = tmp_path / f"round_trip_{unique_id}.chat"
        round_trip_path.write_text(printed_json)

        # Step 5: Re-parse
        result2 = parse_chat_file(round_trip_path)
        assert isinstance(result2, ChatFile), f"Expected ChatFile on re-parse, got ParseError: {result2}"

        # Step 6: Assert the two ChatFile objects are deeply equal
        assert result1.messages == result2.messages, (
            f"Messages differ:\n  first:  {result1.messages}\n  second: {result2.messages}"
        )
        assert result1.metadata == result2.metadata, (
            f"Metadata differs:\n  first:  {result1.metadata}\n  second: {result2.metadata}"
        )
        assert result1.raw_data == result2.raw_data, (
            f"raw_data differs:\n  first:  {result1.raw_data}\n  second: {result2.raw_data}"
        )


# Feature: kiro-cleaner-python, Property 15: Chat structural validation
import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# --- Strategies for generating invalid chat structures ---

# Strategy: valid JSON objects missing the "chat" field
_valid_metadata_st = st.fixed_dictionaries({
    "modelId": st.text(min_size=1, max_size=50),
    "modelProvider": st.text(min_size=1, max_size=50),
    "workflow": st.text(min_size=1, max_size=50),
})

_missing_chat_field_st = st.fixed_dictionaries({
    "metadata": _valid_metadata_st,
}).flatmap(
    lambda base: st.fixed_dictionaries({
        "extra": st.text(min_size=0, max_size=20),
    }).map(lambda extra: {**base, **{k: v for k, v in extra.items() if k != "chat"}})
)

# Strategy: valid JSON objects missing the "metadata" field
_valid_message_st = st.fixed_dictionaries({
    "role": st.sampled_from(["human", "bot", "tool"]),
    "content": st.text(min_size=0, max_size=100),
})

_missing_metadata_field_st = st.fixed_dictionaries({
    "chat": st.lists(_valid_message_st, min_size=1, max_size=5),
}).flatmap(
    lambda base: st.fixed_dictionaries({
        "extra": st.text(min_size=0, max_size=20),
    }).map(lambda extra: {**base, **{k: v for k, v in extra.items() if k != "metadata"}})
)

# Strategy: valid JSON objects with invalid roles in chat messages
_invalid_role_st = st.text(min_size=1, max_size=30).filter(
    lambda r: r not in {"human", "bot", "tool"}
)

_invalid_role_message_st = st.fixed_dictionaries({
    "role": _invalid_role_st,
    "content": st.text(min_size=0, max_size=100),
})


def _chat_with_invalid_role():
    """Generate a chat file structure with at least one invalid role message."""
    return st.tuples(
        st.lists(_valid_message_st, min_size=0, max_size=3),
        _invalid_role_message_st,
        st.lists(_valid_message_st, min_size=0, max_size=3),
    ).map(
        lambda parts: {
            "chat": parts[0] + [parts[1]] + parts[2],
            "metadata": {
                "modelId": "test-model",
                "modelProvider": "test-provider",
                "workflow": "test-workflow",
            },
        }
    )


@pytest.mark.property
class TestChatStructuralValidation:
    """Property 15: Chat structural validation.

    For any valid JSON object that is missing the required 'chat' array,
    or missing the 'metadata' object, or contains a message with a 'role'
    value other than 'human', 'bot', or 'tool', the parser shall return a
    validation error indicating the specific structural violation rather
    than a successfully parsed ChatFile.

    **Validates: Requirements 11.5**
    """

    @given(data=_missing_chat_field_st)
    @settings(max_examples=100)
    def test_missing_chat_field_returns_parse_error(self, data):
        """Objects missing the 'chat' array must produce a ParseError mentioning 'chat'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".chat", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        try:
            result = parse_chat_file(path)

            assert isinstance(result, ParseError), (
                f"Expected ParseError for missing 'chat' field, got {type(result).__name__}"
            )
            assert "chat" in result.reason.lower(), (
                f"ParseError reason should mention 'chat', got: {result.reason}"
            )
        finally:
            path.unlink(missing_ok=True)

    @given(data=_missing_metadata_field_st)
    @settings(max_examples=100)
    def test_missing_metadata_field_returns_parse_error(self, data):
        """Objects missing the 'metadata' object must produce a ParseError mentioning 'metadata'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".chat", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        try:
            result = parse_chat_file(path)

            assert isinstance(result, ParseError), (
                f"Expected ParseError for missing 'metadata' field, got {type(result).__name__}"
            )
            assert "metadata" in result.reason.lower(), (
                f"ParseError reason should mention 'metadata', got: {result.reason}"
            )
        finally:
            path.unlink(missing_ok=True)

    @given(data=_chat_with_invalid_role())
    @settings(max_examples=100)
    def test_invalid_role_returns_parse_error(self, data):
        """Messages with roles not in {human, bot, tool} must produce a ParseError mentioning the invalid role."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".chat", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        try:
            result = parse_chat_file(path)

            assert isinstance(result, ParseError), (
                f"Expected ParseError for invalid role, got {type(result).__name__}"
            )
            assert "role" in result.reason.lower(), (
                f"ParseError reason should mention 'role', got: {result.reason}"
            )
        finally:
            path.unlink(missing_ok=True)
