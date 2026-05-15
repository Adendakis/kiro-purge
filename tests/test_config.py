"""Tests for the config manager module."""

import json
from pathlib import Path

import pytest

from kiro_cleaner.config_manager import (
    AppConfig,
    load_config,
    save_config,
    update_config,
)


class TestAppConfig:
    """Tests for AppConfig dataclass defaults."""

    def test_default_values(self):
        config = AppConfig()
        assert config.keep_logs is False
        assert config.keep_cache is False
        assert config.keep_chats is False
        assert config.keep_index is False
        assert config.keep_recent == 0
        assert config.skip_confirm is False
        assert config.backup_dir == "~/.kiro-cleaner/backups/"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_returns_defaults_when_file_missing(self, tmp_path):
        config_path = tmp_path / "nonexistent" / "config.json"
        config = load_config(config_path)
        assert config == AppConfig()

    def test_loads_valid_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        data = {
            "keep_logs": True,
            "keep_cache": False,
            "keep_chats": True,
            "keep_index": False,
            "keep_recent": 14,
            "skip_confirm": True,
            "backup_dir": "/custom/backups/",
        }
        config_path.write_text(json.dumps(data))

        config = load_config(config_path)
        assert config.keep_logs is True
        assert config.keep_chats is True
        assert config.keep_recent == 14
        assert config.skip_confirm is True
        assert config.backup_dir == "/custom/backups/"

    def test_returns_defaults_for_invalid_json(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{")

        config = load_config(config_path)
        assert config == AppConfig()

    def test_returns_defaults_for_non_dict_json(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps([1, 2, 3]))

        config = load_config(config_path)
        assert config == AppConfig()

    def test_ignores_unknown_keys(self, tmp_path):
        config_path = tmp_path / "config.json"
        data = {"keep_logs": True, "unknown_key": "value"}
        config_path.write_text(json.dumps(data))

        config = load_config(config_path)
        assert config.keep_logs is True

    def test_uses_default_for_wrong_type_values(self, tmp_path):
        config_path = tmp_path / "config.json"
        data = {
            "keep_logs": "not_a_bool",
            "keep_recent": "not_an_int",
            "backup_dir": 123,
        }
        config_path.write_text(json.dumps(data))

        config = load_config(config_path)
        assert config.keep_logs is False  # default
        assert config.keep_recent == 0  # default
        assert config.backup_dir == "~/.kiro-cleaner/backups/"  # default

    def test_partial_config_fills_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        data = {"keep_logs": True}
        config_path.write_text(json.dumps(data))

        config = load_config(config_path)
        assert config.keep_logs is True
        assert config.keep_cache is False  # default
        assert config.keep_recent == 0  # default


class TestSaveConfig:
    """Tests for save_config function."""

    def test_saves_config_to_disk(self, tmp_path):
        config_path = tmp_path / "config.json"
        config = AppConfig(keep_logs=True, keep_recent=7)

        save_config(config, config_path)

        data = json.loads(config_path.read_text())
        assert data["keep_logs"] is True
        assert data["keep_recent"] == 7
        assert data["skip_confirm"] is False

    def test_creates_parent_directories(self, tmp_path):
        config_path = tmp_path / "nested" / "dir" / "config.json"

        save_config(AppConfig(), config_path)

        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["keep_logs"] is False

    def test_overwrites_existing_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"keep_logs": False}))

        save_config(AppConfig(keep_logs=True), config_path)

        data = json.loads(config_path.read_text())
        assert data["keep_logs"] is True

    def test_raises_on_write_failure(self, tmp_path):
        # Point to a path where we can't write (directory as file)
        config_path = tmp_path / "readonly_dir" / "subdir" / "config.json"
        (tmp_path / "readonly_dir").mkdir()
        (tmp_path / "readonly_dir").chmod(0o444)

        with pytest.raises(OSError):
            save_config(AppConfig(), config_path)

        # Restore permissions for cleanup
        (tmp_path / "readonly_dir").chmod(0o755)


class TestUpdateConfig:
    """Tests for update_config function."""

    def test_update_bool_field_true(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        result = update_config("keep_logs", "true", config_path)
        assert result.keep_logs is True

        # Verify persisted
        loaded = load_config(config_path)
        assert loaded.keep_logs is True

    def test_update_bool_field_false(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(keep_logs=True), config_path)

        result = update_config("keep_logs", "false", config_path)
        assert result.keep_logs is False

    def test_update_bool_case_insensitive(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        result = update_config("keep_cache", "True", config_path)
        assert result.keep_cache is True

        result = update_config("keep_cache", "FALSE", config_path)
        assert result.keep_cache is False

    def test_update_int_field(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        result = update_config("keep_recent", "14", config_path)
        assert result.keep_recent == 14

    def test_update_str_field(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        result = update_config("backup_dir", "/my/backups/", config_path)
        assert result.backup_dir == "/my/backups/"

    def test_invalid_key_raises_valueerror(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        with pytest.raises(ValueError, match="Unrecognized configuration key"):
            update_config("nonexistent_key", "value", config_path)

    def test_invalid_bool_value_raises_valueerror(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        with pytest.raises(ValueError, match="expected 'true' or 'false'"):
            update_config("keep_logs", "yes", config_path)

    def test_invalid_int_value_raises_valueerror(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(), config_path)

        with pytest.raises(ValueError, match="expected an integer"):
            update_config("keep_recent", "not_a_number", config_path)

    def test_update_creates_config_if_missing(self, tmp_path):
        config_path = tmp_path / "new_config.json"

        result = update_config("keep_logs", "true", config_path)
        assert result.keep_logs is True
        assert config_path.exists()

    def test_update_preserves_other_fields(self, tmp_path):
        config_path = tmp_path / "config.json"
        save_config(AppConfig(keep_logs=True, keep_recent=7), config_path)

        result = update_config("keep_cache", "true", config_path)
        assert result.keep_logs is True  # preserved
        assert result.keep_recent == 7  # preserved
        assert result.keep_cache is True  # updated


# Feature: kiro-cleaner-python, Property 10: Config set/get round-trip
import tempfile

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Strategies for generating valid config key-value pairs
_bool_keys = st.sampled_from(["keep_logs", "keep_cache", "keep_chats", "keep_index", "skip_confirm"])
_int_keys = st.just("keep_recent")
_str_keys = st.just("backup_dir")

_bool_values = st.booleans()
_int_values = st.integers(min_value=-1000, max_value=1000)
_str_values = st.text(min_size=1, max_size=100)


@st.composite
def config_key_value(draw):
    """Generate a random valid config key and a value of the correct type."""
    key_type = draw(st.sampled_from(["bool", "int", "str"]))
    if key_type == "bool":
        key = draw(_bool_keys)
        value = draw(_bool_values)
        str_value = "true" if value else "false"
        return key, str_value, value
    elif key_type == "int":
        key = draw(_int_keys)
        value = draw(_int_values)
        str_value = str(value)
        return key, str_value, value
    else:
        key = draw(_str_keys)
        value = draw(_str_values)
        str_value = value
        return key, str_value, value


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=config_key_value())
def test_config_set_get_round_trip(tmp_path, data):
    """Property 10: For any valid configuration key and for any value of the
    correct type for that key, setting the configuration value and then loading
    the configuration shall return the same value that was set.

    **Validates: Requirements 8.3**
    """
    key, str_value, expected_value = data
    # Use a unique config file per example to avoid cross-contamination
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.json"

        # Set the config value
        update_config(key, str_value, config_path)

        # Load the config and verify the round-trip
        loaded = load_config(config_path)
        actual_value = getattr(loaded, key)

        assert actual_value == expected_value, (
            f"Round-trip failed for key={key!r}: "
            f"set {str_value!r}, expected {expected_value!r}, got {actual_value!r}"
        )
