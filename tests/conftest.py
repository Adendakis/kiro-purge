"""Shared test fixtures for kiro-cleaner tests."""

import os
import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test use."""
    return tmp_path


@pytest.fixture
def mock_kiro_storage(tmp_path):
    """Create a realistic mock Kiro storage directory tree for testing.

    Structure mirrors the actual Kiro IDE storage layout:
        logs/
        Cache/
        CachedData/
        GPUCache/
        User/globalStorage/kiro.kiroagent/
        User/globalStorage/kiro.kiroagent/index/
        User/History/
        Crashpad/
    """
    storage = tmp_path / "kiro_storage"
    storage.mkdir()

    # logs/
    logs_dir = storage / "logs"
    logs_dir.mkdir()
    (logs_dir / "2024-01-10.log").write_text("log entry 1\n")
    (logs_dir / "2024-01-11.log").write_text("log entry 2\nmore logs\n")

    # Cache/
    cache_dir = storage / "Cache"
    cache_dir.mkdir()
    (cache_dir / "data_0").write_bytes(b"\x00" * 1024)
    (cache_dir / "data_1").write_bytes(b"\x00" * 2048)

    # CachedData/
    cached_data_dir = storage / "CachedData"
    cached_data_dir.mkdir()
    (cached_data_dir / "index.json").write_text('{"version": 1}')

    # GPUCache/
    gpu_cache_dir = storage / "GPUCache"
    gpu_cache_dir.mkdir()
    (gpu_cache_dir / "gpu_data").write_bytes(b"\x01" * 512)

    # User/globalStorage/kiro.kiroagent/ (chats and index)
    agent_dir = storage / "User" / "globalStorage" / "kiro.kiroagent"
    agent_dir.mkdir(parents=True)

    # Chat files
    chat1 = {
        "chat": [
            {"role": "human", "content": "Hello, how are you?"},
            {"role": "bot", "content": "I'm doing well, thanks!"},
        ],
        "metadata": {
            "modelId": "claude-3",
            "modelProvider": "anthropic",
            "workflow": "chat",
            "startTime": 1700000000000,
            "endTime": 1700000060000,
        },
    }
    (agent_dir / "session1.chat").write_text(json.dumps(chat1))

    chat2 = {
        "chat": [
            {"role": "human", "content": "Write a function to sort a list"},
            {"role": "bot", "content": "Here's a sorting function..."},
            {"role": "tool", "content": "def sort_list(items): return sorted(items)"},
        ],
        "metadata": {
            "modelId": "claude-3",
            "modelProvider": "anthropic",
            "workflow": "code",
            "startTime": 1700100000000,
            "endTime": 1700100120000,
        },
    }
    (agent_dir / "session2.chat").write_text(json.dumps(chat2))

    # Index directory
    index_dir = agent_dir / "index"
    index_dir.mkdir()
    (index_dir / "vectors.bin").write_bytes(b"\x02" * 256)
    (index_dir / "metadata.json").write_text('{"entries": 100}')

    # User/History/
    history_dir = storage / "User" / "History"
    history_dir.mkdir(parents=True)
    (history_dir / "entry1.json").write_text('{"file": "main.py", "timestamp": 1700000000}')
    (history_dir / "entry2.json").write_text('{"file": "utils.py", "timestamp": 1700050000}')

    # Crashpad/
    crashpad_dir = storage / "Crashpad"
    crashpad_dir.mkdir()
    (crashpad_dir / "crash_2024-01-10.dmp").write_bytes(b"\x03" * 4096)

    # Protected files (should never be deleted)
    (storage / "config.json").write_text('{"theme": "dark"}')
    (storage / "settings.json").write_text('{"editor.fontSize": 14}')

    # Temp files scattered around
    (storage / "temp_file.tmp").write_bytes(b"\x04" * 128)
    (logs_dir / "debug.temp").write_bytes(b"\x05" * 64)

    return storage


@pytest.fixture
def mock_chat_file(tmp_path):
    """Create a single valid chat file for testing."""
    chat_data = {
        "chat": [
            {"role": "human", "content": "Test message"},
            {"role": "bot", "content": "Test response"},
        ],
        "metadata": {
            "modelId": "test-model",
            "modelProvider": "test-provider",
            "workflow": "test-workflow",
            "startTime": 1700000000000,
            "endTime": 1700000060000,
        },
    }
    chat_path = tmp_path / "test.chat"
    chat_path.write_text(json.dumps(chat_data))
    return chat_path


@pytest.fixture
def mock_config_dir(tmp_path):
    """Create a temporary config directory for testing configuration management."""
    config_dir = tmp_path / ".kiro-cleaner"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def empty_kiro_storage(tmp_path):
    """Create an empty Kiro storage directory (no artefacts)."""
    storage = tmp_path / "kiro_storage"
    storage.mkdir()
    return storage


@pytest.fixture
def mock_protected_storage(tmp_path):
    """Create a Kiro storage with only protected files and directories."""
    storage = tmp_path / "kiro_storage"
    storage.mkdir()

    # Protected files
    (storage / "config.json").write_text("{}")
    (storage / "settings.json").write_text("{}")
    (storage / "mcp.json").write_text("{}")
    (storage / "sessions.json").write_text("{}")
    (storage / "state.vscdb").write_bytes(b"\x00" * 64)
    (storage / "workspace.json").write_text("{}")
    (storage / "storage.json").write_text("{}")

    # Protected directories
    agent_dir = storage / "User" / "globalStorage" / "kiro.kiroagent"
    agent_dir.mkdir(parents=True)

    index_dir = agent_dir / "index"
    index_dir.mkdir()
    (index_dir / "data.bin").write_bytes(b"\x00" * 128)

    migrations_dir = storage / ".migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001.sql").write_text("CREATE TABLE ...")

    lancedb_dir = storage / "lancedb"
    lancedb_dir.mkdir()
    (lancedb_dir / "vectors.lance").write_bytes(b"\x00" * 256)

    return storage
