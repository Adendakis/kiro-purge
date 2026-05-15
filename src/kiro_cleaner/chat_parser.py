"""Chat file parser for Kiro Cleaner.

Parses .chat JSON files containing conversation data with role-based messages
and metadata including timestamps.
"""

from dataclasses import dataclass
from pathlib import Path
import json


VALID_ROLES = {"human", "bot", "tool"}


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str
    content: str


@dataclass
class ChatMetadata:
    """Metadata associated with a chat file."""

    model_id: str
    model_provider: str
    workflow: str
    start_time: int | None = None
    end_time: int | None = None


@dataclass
class ChatFile:
    """A parsed chat file with messages, metadata, and raw data."""

    messages: list[ChatMessage]
    metadata: ChatMetadata
    raw_data: dict


@dataclass
class ParseError:
    """Error returned when a chat file cannot be parsed or validated."""

    path: Path
    reason: str


def parse_chat_file(path: Path) -> ChatFile | ParseError:
    """Parse a .chat JSON file.

    Returns ChatFile on success or ParseError for malformed JSON,
    missing required fields, or invalid role values.
    """
    # Step 1: Read file content
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return ParseError(path=path, reason=f"Cannot read file: {e}")

    # Step 2: Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ParseError(path=path, reason=f"Malformed JSON: {e}")

    if not isinstance(data, dict):
        return ParseError(path=path, reason="Top-level JSON value must be an object")

    # Step 3: Validate "chat" array exists and is a list
    if "chat" not in data:
        return ParseError(path=path, reason='Missing required field: "chat"')

    chat_array = data["chat"]
    if not isinstance(chat_array, list):
        return ParseError(path=path, reason='"chat" must be an array')

    # Step 4 & 5: Validate each message has "role" and "content", and role is valid
    messages: list[ChatMessage] = []
    for i, msg in enumerate(chat_array):
        if not isinstance(msg, dict):
            return ParseError(
                path=path, reason=f"chat[{i}] must be an object"
            )
        if "role" not in msg:
            return ParseError(
                path=path, reason=f'chat[{i}] missing required field: "role"'
            )
        if "content" not in msg:
            return ParseError(
                path=path, reason=f'chat[{i}] missing required field: "content"'
            )

        role = msg["role"]
        if role not in VALID_ROLES:
            return ParseError(
                path=path,
                reason=f'chat[{i}] has invalid role: "{role}". Must be one of: human, bot, tool',
            )

        messages.append(ChatMessage(role=role, content=msg["content"]))

    # Step 6: Validate "metadata" object exists and is a dict
    if "metadata" not in data:
        return ParseError(path=path, reason='Missing required field: "metadata"')

    metadata_obj = data["metadata"]
    if not isinstance(metadata_obj, dict):
        return ParseError(path=path, reason='"metadata" must be an object')

    # Step 7: Validate metadata has required fields
    required_metadata_fields = ["modelId", "modelProvider", "workflow"]
    for field in required_metadata_fields:
        if field not in metadata_obj:
            return ParseError(
                path=path, reason=f'metadata missing required field: "{field}"'
            )

    # Step 8: Extract startTime and endTime (optional)
    start_time = metadata_obj.get("startTime")
    end_time = metadata_obj.get("endTime")

    # Ensure start_time and end_time are int or None
    if start_time is not None and not isinstance(start_time, int):
        start_time = None
    if end_time is not None and not isinstance(end_time, int):
        end_time = None

    metadata = ChatMetadata(
        model_id=metadata_obj["modelId"],
        model_provider=metadata_obj["modelProvider"],
        workflow=metadata_obj["workflow"],
        start_time=start_time,
        end_time=end_time,
    )

    # Step 9: Return ChatFile with parsed data and raw_data preserving original dict
    return ChatFile(messages=messages, metadata=metadata, raw_data=data)


def pretty_print_chat(chat: ChatFile) -> str:
    """Serialize ChatFile back to JSON string preserving all fields.

    Uses the raw_data dict to ensure all original fields and values are preserved.
    """
    return json.dumps(chat.raw_data, indent=2)
