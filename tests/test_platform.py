"""Tests for platform detection and path resolution."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from kiro_cleaner.platform import (
    PlatformInfo,
    resolve_platform,
    kill_kiro_processes,
    _find_kiro_pids_unix,
    _kill_unix,
    _find_kiro_pids_windows,
    _kill_windows,
)


class TestPlatformInfo:
    """Tests for PlatformInfo dataclass."""

    def test_dataclass_fields(self):
        """PlatformInfo stores os_name, kiro_storage, and home_dir."""
        info = PlatformInfo(
            os_name="darwin",
            kiro_storage=Path("/Users/test/Library/Application Support/kiro"),
            home_dir=Path("/Users/test"),
        )
        assert info.os_name == "darwin"
        assert info.kiro_storage == Path("/Users/test/Library/Application Support/kiro")
        assert info.home_dir == Path("/Users/test")


class TestResolvePlatformMacOS:
    """Tests for macOS platform resolution."""

    def test_macos_resolves_correct_path(self, monkeypatch):
        """On macOS, kiro_storage resolves to ~/Library/Application Support/kiro/."""
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/Users/testuser")):
            result = resolve_platform()

        assert result.os_name == "darwin"
        assert result.kiro_storage == Path("/Users/testuser/Library/Application Support/kiro")
        assert result.home_dir == Path("/Users/testuser")

    def test_macos_uses_lowercase_kiro(self, monkeypatch):
        """Directory name is lowercase 'kiro' on macOS."""
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/Users/testuser")):
            result = resolve_platform()

        assert result.kiro_storage.name == "kiro"


class TestResolvePlatformWindows:
    """Tests for Windows platform resolution."""

    def test_windows_resolves_correct_path(self, monkeypatch, tmp_path):
        """On Windows, kiro_storage resolves to %APPDATA%\\kiro\\."""
        monkeypatch.setattr(sys, "platform", "win32")
        fake_appdata = str(tmp_path / "AppData" / "Roaming")
        monkeypatch.setenv("APPDATA", fake_appdata)
        with patch("kiro_cleaner.platform.Path.home", return_value=tmp_path):
            result = resolve_platform()

        assert result.os_name == "win32"
        assert result.kiro_storage == Path(fake_appdata) / "kiro"
        assert result.home_dir == tmp_path

    def test_windows_uses_lowercase_kiro(self, monkeypatch, tmp_path):
        """Directory name is lowercase 'kiro' on Windows."""
        monkeypatch.setattr(sys, "platform", "win32")
        fake_appdata = str(tmp_path / "AppData" / "Roaming")
        monkeypatch.setenv("APPDATA", fake_appdata)
        with patch("kiro_cleaner.platform.Path.home", return_value=tmp_path):
            result = resolve_platform()

        assert result.kiro_storage.name == "kiro"

    def test_windows_missing_appdata_raises_system_exit(self, monkeypatch, tmp_path):
        """On Windows, missing APPDATA raises SystemExit."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        with patch("kiro_cleaner.platform.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc_info:
                resolve_platform()

        assert "APPDATA" in str(exc_info.value)


class TestResolvePlatformLinux:
    """Tests for Linux platform resolution."""

    def test_linux_resolves_correct_path(self, monkeypatch):
        """On Linux, kiro_storage resolves to ~/.config/kiro/."""
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/home/testuser")):
            result = resolve_platform()

        assert result.os_name == "linux"
        assert result.kiro_storage == Path("/home/testuser/.config/kiro")
        assert result.home_dir == Path("/home/testuser")

    def test_linux_uses_lowercase_kiro(self, monkeypatch):
        """Directory name is lowercase 'kiro' on Linux."""
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/home/testuser")):
            result = resolve_platform()

        assert result.kiro_storage.name == "kiro"


class TestResolvePlatformUnsupported:
    """Tests for unsupported platform handling."""

    def test_unsupported_platform_raises_system_exit(self, monkeypatch):
        """Unsupported platform raises SystemExit with descriptive message."""
        monkeypatch.setattr(sys, "platform", "freebsd")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/home/testuser")):
            with pytest.raises(SystemExit) as exc_info:
                resolve_platform()

        assert "Unsupported platform" in str(exc_info.value)
        assert "freebsd" in str(exc_info.value)

    def test_another_unsupported_platform(self, monkeypatch):
        """Another unsupported platform also raises SystemExit."""
        monkeypatch.setattr(sys, "platform", "aix")
        with patch("kiro_cleaner.platform.Path.home", return_value=Path("/home/testuser")):
            with pytest.raises(SystemExit) as exc_info:
                resolve_platform()

        assert "Unsupported platform" in str(exc_info.value)


class TestKillKiroProcessesNoProcesses:
    """Tests for kill_kiro_processes when no processes are running."""

    def test_no_processes_returns_empty_list_unix(self, monkeypatch):
        """When no Kiro processes are running on Unix, returns empty list."""
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("kiro_cleaner.platform._find_kiro_pids_unix", return_value=[]):
            result = kill_kiro_processes()
        assert result == []

    def test_no_processes_returns_empty_list_windows(self, monkeypatch):
        """When no Kiro processes are running on Windows, returns empty list."""
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("kiro_cleaner.platform._find_kiro_pids_windows", return_value=[]):
            result = kill_kiro_processes()
        assert result == []


class TestFindKiroPidsUnix:
    """Tests for _find_kiro_pids_unix."""

    def test_finds_pids_from_pgrep(self):
        """Parses PIDs from pgrep output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1234\n5678\n"
        with patch("kiro_cleaner.platform.subprocess.run", return_value=mock_result):
            pids = _find_kiro_pids_unix()
        assert pids == [1234, 5678]

    def test_returns_empty_when_pgrep_finds_nothing(self):
        """Returns empty list when pgrep finds no matches."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("kiro_cleaner.platform.subprocess.run", return_value=mock_result):
            pids = _find_kiro_pids_unix()
        assert pids == []

    def test_handles_pgrep_not_found(self):
        """Returns empty list when pgrep is not available."""
        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=FileNotFoundError("pgrep not found"),
        ):
            pids = _find_kiro_pids_unix()
        assert pids == []


class TestKillUnix:
    """Tests for _kill_unix process termination."""

    def test_successful_sigterm(self):
        """Process exits after SIGTERM, no warnings."""
        # os.kill(pid, SIGTERM) succeeds, then os.kill(pid, 0) raises ProcessLookupError
        def mock_kill(pid, sig):
            if sig == 0:
                raise ProcessLookupError()

        with patch("kiro_cleaner.platform.os.kill", side_effect=mock_kill):
            warnings = _kill_unix([1234], timeout=2)
        assert warnings == []

    def test_process_already_exited(self):
        """Process already gone when SIGTERM is sent."""
        with patch(
            "kiro_cleaner.platform.os.kill",
            side_effect=ProcessLookupError(),
        ):
            warnings = _kill_unix([1234], timeout=2)
        assert warnings == []

    def test_permission_denied_on_sigterm(self):
        """Permission error on SIGTERM produces warning."""
        with patch(
            "kiro_cleaner.platform.os.kill",
            side_effect=PermissionError("Operation not permitted"),
        ):
            warnings = _kill_unix([1234], timeout=2)
        assert len(warnings) == 1
        assert "Permission denied" in warnings[0]
        assert "1234" in warnings[0]

    def test_sigkill_after_timeout(self):
        """Process gets SIGKILL after not responding to SIGTERM within timeout."""
        import signal as sig_mod

        def mock_kill(pid, sig):
            if sig == sig_mod.SIGTERM:
                return  # SIGTERM sent successfully
            elif sig == sig_mod.SIGKILL:
                return  # SIGKILL sent successfully
            elif sig == 0:
                # Post-SIGKILL verification: process is gone
                raise ProcessLookupError()

        # time.time() calls: deadline calc (returns 0), loop check (returns 100 > deadline=1, exits)
        with patch("kiro_cleaner.platform.os.kill", side_effect=mock_kill):
            with patch("kiro_cleaner.platform.time.sleep"):
                with patch("kiro_cleaner.platform.time.time", side_effect=[0, 100]):
                    warnings = _kill_unix([1234], timeout=1)
        assert warnings == []

    def test_permission_denied_on_sigkill(self):
        """Permission error on SIGKILL produces warning."""
        import signal as sig_mod

        call_count = [0]

        def mock_kill(pid, sig):
            if sig == sig_mod.SIGTERM:
                return
            elif sig == 0:
                return  # Process always appears running
            elif sig == sig_mod.SIGKILL:
                raise PermissionError("Operation not permitted")

        with patch("kiro_cleaner.platform.os.kill", side_effect=mock_kill):
            with patch("kiro_cleaner.platform.time.sleep"):
                with patch("kiro_cleaner.platform.time.time", side_effect=[0, 100]):
                    warnings = _kill_unix([1234], timeout=1)
        assert len(warnings) == 1
        assert "Permission denied" in warnings[0]
        assert "force-kill" in warnings[0]


class TestFindKiroPidsWindows:
    """Tests for _find_kiro_pids_windows."""

    def test_finds_pids_from_tasklist(self):
        """Parses PIDs from tasklist CSV output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '"kiro.exe","1234","Console","1","50,000 K"\n'
        with patch("kiro_cleaner.platform.subprocess.run", return_value=mock_result):
            pids = _find_kiro_pids_windows()
        assert pids == ["1234"]

    def test_returns_empty_when_no_kiro_processes(self):
        """Returns empty list when no kiro processes found."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("kiro_cleaner.platform.subprocess.run", return_value=mock_result):
            pids = _find_kiro_pids_windows()
        assert pids == []

    def test_handles_tasklist_not_found(self):
        """Returns empty list when tasklist is not available."""
        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=FileNotFoundError("tasklist not found"),
        ):
            pids = _find_kiro_pids_windows()
        assert pids == []


class TestKillWindows:
    """Tests for _kill_windows process termination."""

    def test_successful_taskkill(self):
        """Process exits after taskkill, no warnings."""
        mock_taskkill = MagicMock()
        mock_taskkill.returncode = 0
        mock_taskkill.stdout = ""

        mock_check = MagicMock()
        mock_check.returncode = 0
        mock_check.stdout = "INFO: No tasks are running"

        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=[mock_taskkill, mock_check],
        ):
            warnings = _kill_windows(["1234"], timeout=2)
        assert warnings == []

    def test_taskkill_fails_force_succeeds(self):
        """When graceful taskkill fails, force kill succeeds."""
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stderr = "Access denied"

        mock_force = MagicMock()
        mock_force.returncode = 0
        mock_force.stdout = ""

        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=[mock_fail, mock_force],
        ):
            warnings = _kill_windows(["1234"], timeout=2)
        assert warnings == []

    def test_both_taskkill_attempts_fail(self):
        """When both graceful and force taskkill fail, produces warning."""
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stderr = "Access denied"

        mock_force_fail = MagicMock()
        mock_force_fail.returncode = 1
        mock_force_fail.stderr = "Access denied"

        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=[mock_fail, mock_force_fail],
        ):
            warnings = _kill_windows(["1234"], timeout=2)
        assert len(warnings) == 1
        assert "1234" in warnings[0]
        assert "could not be terminated" in warnings[0]

    def test_taskkill_command_not_found(self):
        """When taskkill command is not found, produces warning."""
        with patch(
            "kiro_cleaner.platform.subprocess.run",
            side_effect=FileNotFoundError("taskkill not found"),
        ):
            warnings = _kill_windows(["1234"], timeout=2)
        assert len(warnings) == 1
        assert "Failed to run taskkill" in warnings[0]


class TestKillKiroProcessesIntegration:
    """Integration tests for kill_kiro_processes dispatching."""

    def test_dispatches_to_unix_on_darwin(self, monkeypatch):
        """On macOS, uses Unix kill path."""
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("kiro_cleaner.platform._find_kiro_pids_unix", return_value=[1234]) as mock_find:
            with patch("kiro_cleaner.platform._kill_unix", return_value=[]) as mock_kill:
                result = kill_kiro_processes(timeout=5)
        mock_find.assert_called_once()
        mock_kill.assert_called_once_with([1234], 5)
        assert result == []

    def test_dispatches_to_unix_on_linux(self, monkeypatch):
        """On Linux, uses Unix kill path."""
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("kiro_cleaner.platform._find_kiro_pids_unix", return_value=[5678]) as mock_find:
            with patch("kiro_cleaner.platform._kill_unix", return_value=[]) as mock_kill:
                result = kill_kiro_processes(timeout=5)
        mock_find.assert_called_once()
        mock_kill.assert_called_once_with([5678], 5)
        assert result == []

    def test_dispatches_to_windows_on_win32(self, monkeypatch):
        """On Windows, uses Windows kill path."""
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("kiro_cleaner.platform._find_kiro_pids_windows", return_value=["1234"]) as mock_find:
            with patch("kiro_cleaner.platform._kill_windows", return_value=[]) as mock_kill:
                result = kill_kiro_processes(timeout=5)
        mock_find.assert_called_once()
        mock_kill.assert_called_once_with(["1234"], 5)
        assert result == []

    def test_default_timeout_is_10(self, monkeypatch):
        """Default timeout parameter is 10 seconds."""
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("kiro_cleaner.platform._find_kiro_pids_unix", return_value=[100]):
            with patch("kiro_cleaner.platform._kill_unix", return_value=[]) as mock_kill:
                kill_kiro_processes()
        mock_kill.assert_called_once_with([100], 10)
