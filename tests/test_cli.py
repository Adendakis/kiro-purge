"""Integration tests for CLI commands using Click's CliRunner.

Tests full workflows end-to-end:
- Scan → clean → verify
- Backup → delete → restore → verify
- Chat filter → clean → verify
- Config set → config get → verify
- Error cases: missing storage, invalid categories, invalid dates

Requirements: 1.1, 2.1, 5.1, 6.1, 7.1, 8.2
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kiro_cleaner.cli import main
from kiro_cleaner.platform import PlatformInfo


@pytest.fixture
def runner():
    """Provide a Click CliRunner instance."""
    return CliRunner()


@pytest.fixture
def mock_platform(tmp_path):
    """Create a PlatformInfo pointing to a temp directory and patch resolve_platform."""
    kiro_storage = tmp_path / "kiro_storage"
    kiro_storage.mkdir()

    platform_info = PlatformInfo(
        os_name="darwin",
        kiro_storage=kiro_storage,
        home_dir=tmp_path,
    )
    return platform_info


@pytest.fixture
def populated_storage(mock_platform):
    """Create a populated Kiro storage with files in various categories."""
    storage = mock_platform.kiro_storage

    # logs/
    logs_dir = storage / "logs"
    logs_dir.mkdir()
    (logs_dir / "old.log").write_text("old log entry\n")
    (logs_dir / "recent.log").write_text("recent log entry\n")

    # Make old.log appear old (modify time to 30 days ago)
    old_time = time.time() - (30 * 24 * 3600)
    os.utime(logs_dir / "old.log", (old_time, old_time))

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

    # User/globalStorage/kiro.kiroagent/ (chats)
    agent_dir = storage / "User" / "globalStorage" / "kiro.kiroagent"
    agent_dir.mkdir(parents=True)

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
            {"role": "human", "content": "Write a sorting function"},
            {"role": "bot", "content": "Here's a sort implementation..."},
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

    # Make chat files old enough to be eligible for deletion
    for chat_file in agent_dir.glob("*.chat"):
        os.utime(chat_file, (old_time, old_time))

    # index/ (protected directory)
    index_dir = agent_dir / "index"
    index_dir.mkdir()
    (index_dir / "vectors.bin").write_bytes(b"\x02" * 256)

    # User/History/
    history_dir = storage / "User" / "History"
    history_dir.mkdir(parents=True)
    (history_dir / "entry1.json").write_text('{"file": "main.py"}')
    os.utime(history_dir / "entry1.json", (old_time, old_time))

    # Crashpad/
    crashpad_dir = storage / "Crashpad"
    crashpad_dir.mkdir()
    (crashpad_dir / "crash.dmp").write_bytes(b"\x03" * 4096)
    os.utime(crashpad_dir / "crash.dmp", (old_time, old_time))

    # Temp files
    (storage / "temp_file.tmp").write_bytes(b"\x04" * 128)

    # Protected files
    (storage / "config.json").write_text('{"theme": "dark"}')
    (storage / "settings.json").write_text('{"editor.fontSize": 14}')

    return storage


class TestScanWorkflow:
    """Test scan command integration."""

    def test_scan_displays_categories_and_sizes(self, runner, mock_platform, populated_storage):
        """Scan should display all categories with file counts and sizes."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["scan"])

        assert result.exit_code == 0
        # Check that category names appear in output
        assert "logs" in result.output
        assert "cache" in result.output
        assert "chats" in result.output
        assert "Total" in result.output

    def test_scan_missing_storage_exits_with_error(self, runner, tmp_path):
        """Scan with non-existent storage should exit with code 1."""
        platform_info = PlatformInfo(
            os_name="darwin",
            kiro_storage=tmp_path / "nonexistent",
            home_dir=tmp_path,
        )
        with patch("kiro_cleaner.cli.resolve_platform", return_value=platform_info):
            result = runner.invoke(main, ["scan"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "ERROR" in result.output

    def test_scan_shows_sessions_category(self, runner, mock_platform, populated_storage):
        """The default scan output includes the new 'sessions' category."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["scan"])

        assert result.exit_code == 0
        assert "sessions" in result.output

    def test_scan_suggest_reports_tiers(self, runner, mock_platform):
        """scan --suggest prints safety tiers and is read-only."""
        storage = mock_platform.kiro_storage
        # Some disposable data (safe tier) and an old session for a missing project.
        logs = storage / "logs"
        logs.mkdir()
        (logs / "a.log").write_text("log data")

        hash_dir = (
            storage / "User" / "globalStorage" / "kiro.kiroagent"
            / "ffee0011223344556677889900aabbcc" / "inner"
        )
        hash_dir.mkdir(parents=True)
        session = {
            "documentUri": "file:///Users/tester/deleted-project/main.py",
            "padding": "z" * 30000,
        }
        (hash_dir / "spec.json").write_text(json.dumps(session))
        (hash_dir / "biglog").write_bytes(b"\x00" * 4096)
        # Age the session data beyond retention.
        old = time.time() - 300 * 86400
        for p in hash_dir.rglob("*"):
            if p.is_file():
                os.utime(p, (old, old))

        ws = storage / "User" / "workspaceStorage" / "aabbccddeeff0011"
        ws.mkdir(parents=True)
        (ws / "workspace.json").write_text(
            json.dumps({"folder": "file:///Users/tester/deleted-project"})
        )

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["scan", "--suggest"])

        assert result.exit_code == 0
        assert "SAFE" in result.output
        assert "reclaimable" in result.output.lower()
        # /Users/tester/deleted-project has no folder on disk -> project-scoped hint.
        assert "clean --project" in result.output
        assert "/Users/tester/deleted-project" in result.output

    def test_scan_by_project_groups_by_folder(self, runner, mock_platform):
        """scan --by-project groups storage by owning project folder."""
        storage = mock_platform.kiro_storage
        # Build a kiroagent workspace-hash dir with a session log referencing a project.
        hash_dir = (
            storage
            / "User" / "globalStorage" / "kiro.kiroagent"
            / "abc123def456abc123def456abc123de" / "inner"
        )
        hash_dir.mkdir(parents=True)
        session = {
            "executionId": "x",
            "workflowType": "act",
            "documentUri": "file:///Users/tester/projects/demo/main.py",
            "padding": "z" * 30000,
        }
        (hash_dir / "6f65f441d88ae5611b78bd3a67637f07").write_text(json.dumps(session))

        # Authoritative project folder via a workspaceStorage entry.
        ws = storage / "User" / "workspaceStorage" / "0011223344556677"
        ws.mkdir(parents=True)
        (ws / "workspace.json").write_text(
            json.dumps({"folder": "file:///Users/tester/projects/demo"})
        )

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["scan", "--by-project"])

        assert result.exit_code == 0
        assert "Project" in result.output
        assert "/Users/tester/projects/demo" in result.output
        assert "Sessions" in result.output


class TestCleanWorkflow:
    """Test clean command integration."""

    def test_clean_with_category_and_force(self, runner, mock_platform, populated_storage):
        """Clean with --category and --force should delete files in that category."""
        storage = populated_storage

        # Verify cache files exist before cleaning
        assert (storage / "Cache" / "data_0").exists()
        assert (storage / "Cache" / "data_1").exists()

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["clean", "--category", "cache", "--force"])

        assert result.exit_code == 0
        # Cache files should be deleted
        assert not (storage / "Cache" / "data_0").exists()
        assert not (storage / "Cache" / "data_1").exists()
        # CachedData and GPUCache should also be cleaned
        assert not (storage / "CachedData" / "index.json").exists()
        assert not (storage / "GPUCache" / "gpu_data").exists()

    def _seed_project(self, storage, project="/Users/tester/demo-proj"):
        """Create a kiroagent hash dir resolvable to `project`, plus an index/."""
        hd = (
            storage / "User" / "globalStorage" / "kiro.kiroagent"
            / "abc0011223344556677889900aabbccd" / "inner"
        )
        hd.mkdir(parents=True)
        (hd / "spec.json").write_text(
            json.dumps({"documentUri": f"file://{project}/requirements.md"})
        )
        (hd / "session_a").write_bytes(b"\x00" * 2048)
        (hd / "session_b").write_bytes(b"\x00" * 1024)
        # A per-workspace index/ that must be protected from project-scoped delete.
        idx = hd.parent / "index"
        idx.mkdir()
        (idx / "segment_0").write_bytes(b"\x00" * 4096)
        ws = storage / "User" / "workspaceStorage" / "1122334455667788"
        ws.mkdir(parents=True)
        (ws / "workspace.json").write_text(
            json.dumps({"folder": f"file://{project}"})
        )
        return hd, idx

    def test_clean_project_dry_run_scoped(self, runner, mock_platform):
        """clean --project --dry-run reports the project and deletes nothing."""
        storage = mock_platform.kiro_storage
        hd, idx = self._seed_project(storage)

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(
                main, ["clean", "--project", "/Users/tester/demo-proj", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "Cleaning project: /Users/tester/demo-proj" in result.output
        assert "Would delete" in result.output
        # Nothing actually removed.
        assert (hd / "session_a").exists()
        assert (idx / "segment_0").exists()

    def test_clean_project_force_deletes_only_project(self, runner, mock_platform):
        """clean --project --force deletes the project's files but not its index."""
        storage = mock_platform.kiro_storage
        hd, idx = self._seed_project(storage)
        # An unrelated project's file that must survive.
        other = (
            storage / "User" / "globalStorage" / "kiro.kiroagent"
            / "ffffeeeeddddccccbbbbaaaa99998888" / "s"
        )
        other.mkdir(parents=True)
        (other / "keep_me").write_bytes(b"\x00" * 512)

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(
                main, ["clean", "--project", "/Users/tester/demo-proj", "--force"]
            )

        assert result.exit_code == 0
        assert not (hd / "session_a").exists()      # project data deleted
        assert not (hd / "session_b").exists()
        assert (idx / "segment_0").exists()          # index protected
        assert (other / "keep_me").exists()          # other project untouched

    def test_clean_project_mutually_exclusive_with_category(self, runner, mock_platform):
        """--project cannot be combined with --category."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--project", "/Users/tester/demo-proj",
                "--category", "cache", "--force",
            ])
        assert result.exit_code == 1
        assert "mutually" in result.output.lower() or "cannot be combined" in result.output.lower()

    def test_clean_project_not_found_exits_cleanly(self, runner, mock_platform):
        """A --project with no attributed files reports nothing to do."""
        storage = mock_platform.kiro_storage
        self._seed_project(storage)
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(
                main, ["clean", "--project", "/Users/tester/no-such-project", "--force"]
            )
        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_clean_preserves_protected_files(self, runner, mock_platform, populated_storage):
        """Clean should never delete protected files."""
        storage = populated_storage

        # Clean all categories
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "logs", "--category", "cache",
                "--category", "chats", "--category", "temp",
                "--category", "history", "--category", "crash_reports",
                "--force",
            ])

        assert result.exit_code == 0
        # Protected files must still exist
        assert (storage / "config.json").exists()
        assert (storage / "settings.json").exists()
        # Protected directory contents must still exist
        index_dir = storage / "User" / "globalStorage" / "kiro.kiroagent" / "index"
        assert (index_dir / "vectors.bin").exists()

    def test_clean_dry_run_does_not_delete(self, runner, mock_platform, populated_storage):
        """Clean with --dry-run should not delete any files."""
        storage = populated_storage

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "cache", "--dry-run", "--force",
            ])

        assert result.exit_code == 0
        # Files should still exist
        assert (storage / "Cache" / "data_0").exists()
        assert (storage / "Cache" / "data_1").exists()
        # Output should indicate what would be deleted
        assert "Would delete" in result.output or "delete" in result.output.lower()

    def test_clean_keep_recent_invalid_exits_error(self, runner, mock_platform, populated_storage):
        """Clean with --keep-recent 0 should exit with error."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "logs", "--keep-recent", "0", "--force",
            ])

        assert result.exit_code == 1
        assert "ERROR" in result.output or "positive" in result.output.lower()


class TestBackupRestoreWorkflow:
    """Test backup → delete → restore → verify workflow."""

    def test_backup_and_restore_round_trip(self, runner, mock_platform, populated_storage, tmp_path):
        """Backup before clean, then restore should bring files back."""
        storage = populated_storage
        backup_dir = tmp_path / "backups"

        # Patch config to use our temp backup dir
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform), \
             patch("kiro_cleaner.cli.load_config") as mock_load_config:
            from kiro_cleaner.config_manager import AppConfig
            mock_load_config.return_value = AppConfig(backup_dir=str(backup_dir))

            # Clean cache with backup
            result = runner.invoke(main, [
                "clean", "--category", "cache", "--backup", "--force",
            ])

        assert result.exit_code == 0
        assert "Backup created" in result.output

        # Verify cache files are deleted
        assert not (storage / "Cache" / "data_0").exists()
        assert not (storage / "Cache" / "data_1").exists()

        # Find the backup archive
        archives = list(backup_dir.glob("kiro-backup-*.tar.gz"))
        assert len(archives) == 1
        archive_path = archives[0]

        # Restore from backup
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["restore", str(archive_path), "--force"])

        assert result.exit_code == 0
        assert "restored" in result.output.lower() or "Restore" in result.output

        # Verify files are restored
        assert (storage / "Cache" / "data_0").exists()
        assert (storage / "Cache" / "data_1").exists()

    def test_restore_nonexistent_archive_exits_error(self, runner, mock_platform, tmp_path):
        """Restore with non-existent archive should exit with error."""
        fake_archive = tmp_path / "nonexistent.tar.gz"

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["restore", str(fake_archive)])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "ERROR" in result.output


class TestChatFilterWorkflow:
    """Test chat filter → clean → verify workflow."""

    def test_filter_content_cleans_matching_chats(self, runner, mock_platform, populated_storage):
        """Clean with --filter-content should only delete matching chat files."""
        storage = populated_storage
        agent_dir = storage / "User" / "globalStorage" / "kiro.kiroagent"

        # session1.chat contains "Hello, how are you?"
        # session2.chat contains "Write a sorting function"
        assert (agent_dir / "session1.chat").exists()
        assert (agent_dir / "session2.chat").exists()

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "chats",
                "--filter-content", "sorting",
                "--force",
            ])

        assert result.exit_code == 0
        # session2 matches "sorting" and should be deleted
        assert not (agent_dir / "session2.chat").exists()
        # session1 does not match and should remain
        assert (agent_dir / "session1.chat").exists()

    def test_filter_before_date_cleans_old_chats(self, runner, mock_platform, populated_storage):
        """Clean with --filter-before should only delete chats before that date."""
        storage = populated_storage
        agent_dir = storage / "User" / "globalStorage" / "kiro.kiroagent"

        # session1 startTime: 1700000000000 (2023-11-14)
        # session2 startTime: 1700100000000 (2023-11-15)
        # Filter before 2023-11-15 should only match session1

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "chats",
                "--filter-before", "2023-11-15",
                "--force",
            ])

        assert result.exit_code == 0
        # session1 is before 2023-11-15 midnight UTC, should be deleted
        assert not (agent_dir / "session1.chat").exists()
        # session2 is after 2023-11-15 midnight UTC, should remain
        assert (agent_dir / "session2.chat").exists()

    def test_filter_invalid_date_exits_error(self, runner, mock_platform, populated_storage):
        """Clean with invalid date format should exit with error."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "chats",
                "--filter-before", "not-a-date",
                "--force",
            ])

        assert result.exit_code == 1
        assert "Invalid date" in result.output or "ERROR" in result.output


class TestConfigWorkflow:
    """Test config set → config get → verify workflow."""

    def test_config_show_all(self, runner, tmp_path):
        """Config with no args should display all settings."""
        config_path = tmp_path / ".kiro-cleaner" / "config.json"

        with patch("kiro_cleaner.cli.load_config") as mock_load:
            from kiro_cleaner.config_manager import AppConfig
            mock_load.return_value = AppConfig()
            result = runner.invoke(main, ["config"])

        assert result.exit_code == 0
        assert "keep_logs" in result.output
        assert "backup_dir" in result.output
        assert "skip_confirm" in result.output

    def test_config_set_and_get_round_trip(self, runner, tmp_path):
        """Setting a config value and getting it should return the same value."""
        config_path = tmp_path / ".kiro-cleaner" / "config.json"

        with patch("kiro_cleaner.cli.update_config") as mock_update, \
             patch("kiro_cleaner.cli.load_config") as mock_load:
            from kiro_cleaner.config_manager import AppConfig
            updated_config = AppConfig(skip_confirm=True)
            mock_update.return_value = updated_config
            mock_load.return_value = updated_config

            # Set a value
            result = runner.invoke(main, ["config", "skip_confirm", "true"])
            assert result.exit_code == 0
            assert "Updated" in result.output or "skip_confirm" in result.output

            # Get the value back
            result = runner.invoke(main, ["config", "skip_confirm"])
            assert result.exit_code == 0
            assert "True" in result.output or "true" in result.output

    def test_config_set_get_real_round_trip(self, runner, tmp_path):
        """Full round-trip using real config file on disk."""
        config_path = tmp_path / ".kiro-cleaner" / "config.json"

        with patch("kiro_cleaner.config_manager.DEFAULT_CONFIG_PATH", config_path):
            # Set a value
            result = runner.invoke(main, ["config", "skip_confirm", "true"])
            assert result.exit_code == 0

            # Get the value back
            result = runner.invoke(main, ["config", "skip_confirm"])
            assert result.exit_code == 0
            assert "True" in result.output

    def test_config_invalid_key_exits_error(self, runner):
        """Config with invalid key should exit with error."""
        with patch("kiro_cleaner.cli.load_config") as mock_load:
            from kiro_cleaner.config_manager import AppConfig
            mock_load.return_value = AppConfig()
            result = runner.invoke(main, ["config", "nonexistent_key"])

        assert result.exit_code == 1
        assert "Unrecognized" in result.output or "Error" in result.output


class TestErrorCases:
    """Test error cases for various CLI commands."""

    def test_scan_nonexistent_storage(self, runner, tmp_path):
        """Scan with non-existent storage directory should fail."""
        platform_info = PlatformInfo(
            os_name="darwin",
            kiro_storage=tmp_path / "does_not_exist",
            home_dir=tmp_path,
        )
        with patch("kiro_cleaner.cli.resolve_platform", return_value=platform_info):
            result = runner.invoke(main, ["scan"])

        assert result.exit_code == 1

    def test_clean_nonexistent_storage(self, runner, tmp_path):
        """Clean with non-existent storage directory should fail."""
        platform_info = PlatformInfo(
            os_name="darwin",
            kiro_storage=tmp_path / "does_not_exist",
            home_dir=tmp_path,
        )
        with patch("kiro_cleaner.cli.resolve_platform", return_value=platform_info):
            result = runner.invoke(main, [
                "clean", "--category", "logs", "--force",
            ])

        assert result.exit_code == 1

    def test_clean_invalid_category(self, runner, mock_platform, populated_storage):
        """Clean with invalid category should show error."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "invalid_category", "--force",
            ])

        # Click handles invalid choices with exit code 2
        assert result.exit_code == 2
        assert "Invalid value" in result.output or "invalid" in result.output.lower()

    def test_clean_keep_recent_negative(self, runner, mock_platform, populated_storage):
        """Clean with --keep-recent -1 should exit with error."""
        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, [
                "clean", "--category", "logs", "--keep-recent", "-1", "--force",
            ])

        assert result.exit_code == 1

    def test_restore_invalid_archive(self, runner, mock_platform, tmp_path):
        """Restore with invalid (non-tar) file should exit with error."""
        # Create a file that is not a valid tar.gz
        bad_archive = tmp_path / "bad_archive.tar.gz"
        bad_archive.write_text("this is not a tar file")

        with patch("kiro_cleaner.cli.resolve_platform", return_value=mock_platform):
            result = runner.invoke(main, ["restore", str(bad_archive)])

        assert result.exit_code == 1
        assert "Invalid" in result.output or "ERROR" in result.output or "corrupted" in result.output.lower()
