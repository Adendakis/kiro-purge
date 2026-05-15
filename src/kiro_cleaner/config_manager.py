"""Configuration management for Kiro Cleaner.

Handles loading, saving, and updating the tool's configuration stored
at ~/.kiro-cleaner/config.json.
"""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".kiro-cleaner" / "config.json"


@dataclass
class AppConfig:
    """Application configuration with sensible defaults."""

    keep_logs: bool = False
    keep_cache: bool = False
    keep_chats: bool = False
    keep_index: bool = False
    keep_recent: int = 0
    skip_confirm: bool = False
    backup_dir: str = "~/.kiro-cleaner/backups/"


# Type mapping for validation
_BOOL_FIELDS = {"keep_logs", "keep_cache", "keep_chats", "keep_index", "skip_confirm"}
_INT_FIELDS = {"keep_recent"}
_STR_FIELDS = {"backup_dir"}
_VALID_KEYS = _BOOL_FIELDS | _INT_FIELDS | _STR_FIELDS


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from disk or create with defaults.

    If the config file does not exist, returns an AppConfig with default values.
    If the file contains invalid JSON, returns defaults.

    Args:
        config_path: Path to the config file. Defaults to ~/.kiro-cleaner/config.json.

    Returns:
        An AppConfig instance populated from disk or with defaults.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if not path.exists():
        return AppConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()

    if not isinstance(data, dict):
        return AppConfig()

    # Build config from known keys only, using defaults for missing/invalid ones
    kwargs = {}
    for f in fields(AppConfig):
        if f.name in data:
            value = data[f.name]
            # Validate type matches expected
            if f.name in _BOOL_FIELDS and isinstance(value, bool):
                kwargs[f.name] = value
            elif f.name in _INT_FIELDS and isinstance(value, int) and not isinstance(value, bool):
                kwargs[f.name] = value
            elif f.name in _STR_FIELDS and isinstance(value, str):
                kwargs[f.name] = value
            # Otherwise, skip and use default

    return AppConfig(**kwargs)


def save_config(config: AppConfig, config_path: Path | None = None) -> None:
    """Persist configuration to disk.

    Creates parent directories if they don't exist. If writing fails,
    raises an OSError without corrupting the existing config file.

    Args:
        config: The AppConfig instance to save.
        config_path: Path to the config file. Defaults to ~/.kiro-cleaner/config.json.

    Raises:
        OSError: If the config file cannot be written.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    # Create parent directories if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first, then rename for atomicity
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(asdict(config), indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except OSError:
        # Clean up temp file if it exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def update_config(key: str, value: str, config_path: Path | None = None) -> AppConfig:
    """Update a single configuration key with type validation.

    Loads the current config, validates the key and value type,
    updates the field, and persists to disk.

    Args:
        key: The configuration key to update. Must be a recognized key.
        value: The string representation of the new value.
            - Bool fields accept "true" or "false" (case-insensitive).
            - Int fields accept numeric strings.
            - Str fields accept any string.
        config_path: Path to the config file. Defaults to ~/.kiro-cleaner/config.json.

    Returns:
        The updated AppConfig instance.

    Raises:
        ValueError: If the key is unrecognized or the value type doesn't match.
        OSError: If the config file cannot be written.
    """
    if key not in _VALID_KEYS:
        valid_keys = sorted(_VALID_KEYS)
        raise ValueError(
            f"Unrecognized configuration key: '{key}'. "
            f"Valid keys are: {', '.join(valid_keys)}"
        )

    # Parse value based on field type
    if key in _BOOL_FIELDS:
        lower_val = value.lower()
        if lower_val == "true":
            parsed_value = True
        elif lower_val == "false":
            parsed_value = False
        else:
            raise ValueError(
                f"Invalid value for '{key}': expected 'true' or 'false', got '{value}'"
            )
    elif key in _INT_FIELDS:
        try:
            parsed_value = int(value)
        except ValueError:
            raise ValueError(
                f"Invalid value for '{key}': expected an integer, got '{value}'"
            )
    else:
        # String fields accept any value
        parsed_value = value

    path = config_path or DEFAULT_CONFIG_PATH
    config = load_config(path)

    # Update the field
    setattr(config, key, parsed_value)

    # Persist
    save_config(config, path)

    return config
