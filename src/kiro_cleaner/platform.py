"""Platform detection and path resolution for Kiro Cleaner."""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlatformInfo:
    """Platform-specific information for Kiro storage resolution."""

    os_name: str  # "darwin", "win32", "linux"
    kiro_storage: Path  # Resolved Kiro storage path
    home_dir: Path  # User home directory


def resolve_platform() -> PlatformInfo:
    """Detect OS and resolve Kiro storage path.

    Returns:
        PlatformInfo with resolved paths for the current platform.

    Raises:
        SystemExit: On unsupported platform or unresolvable home/APPDATA.
    """
    os_name = sys.platform

    # Resolve home directory
    try:
        home_dir = Path.home()
    except RuntimeError:
        raise SystemExit(
            "Error: Unable to determine home directory. "
            "Cannot resolve Kiro storage path."
        )

    if os_name == "darwin":
        kiro_storage = home_dir / "Library" / "Application Support" / "kiro"
    elif os_name == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise SystemExit(
                "Error: APPDATA environment variable is not set. "
                "Cannot resolve Kiro storage path on Windows."
            )
        kiro_storage = Path(appdata) / "kiro"
    elif os_name == "linux":
        kiro_storage = home_dir / ".config" / "kiro"
    else:
        raise SystemExit(
            f"Error: Unsupported platform '{os_name}'. "
            "Kiro Cleaner supports macOS, Windows, and Linux only."
        )

    return PlatformInfo(
        os_name=os_name,
        kiro_storage=kiro_storage,
        home_dir=home_dir,
    )


def _find_kiro_pids_unix() -> list[int]:
    """Find PIDs of running Kiro processes on Unix systems."""
    pids: list[int] = []
    try:
        result = subprocess.run(
            ["pgrep", "-f", "kiro"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
    except (OSError, FileNotFoundError):
        pass
    return pids


def _kill_unix(pids: list[int], timeout: int) -> list[str]:
    """Terminate processes on Unix: SIGTERM then SIGKILL after timeout."""
    warnings: list[str] = []

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            # Process already exited
            continue
        except PermissionError:
            warnings.append(
                f"Permission denied when trying to terminate process {pid}"
            )
            continue
        except OSError as e:
            warnings.append(
                f"Failed to send SIGTERM to process {pid}: {e}"
            )
            continue

        # Wait for process to exit
        deadline = time.time() + timeout
        still_running = True
        while time.time() < deadline:
            try:
                os.kill(pid, 0)  # Check if process exists
            except ProcessLookupError:
                still_running = False
                break
            except PermissionError:
                # Process exists but we can't signal it
                still_running = True
                break
            time.sleep(0.5)

        if still_running:
            # Send SIGKILL
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                # Process exited between check and kill
                continue
            except PermissionError:
                warnings.append(
                    f"Permission denied when trying to force-kill process {pid}"
                )
                continue
            except OSError as e:
                warnings.append(
                    f"Failed to force-kill process {pid}: {e}"
                )
                continue

            # Brief wait to confirm SIGKILL worked
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
                # Still running after SIGKILL
                warnings.append(
                    f"Process {pid} could not be terminated after SIGKILL"
                )
            except ProcessLookupError:
                pass  # Successfully killed
            except PermissionError:
                warnings.append(
                    f"Cannot verify termination of process {pid}: permission denied"
                )

    return warnings


def _find_kiro_pids_windows() -> list[str]:
    """Find names/PIDs of running Kiro processes on Windows."""
    pids: list[str] = []
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq kiro*", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.append(parts[1])
    except (OSError, FileNotFoundError):
        pass
    return pids


def _kill_windows(pids: list[str], timeout: int) -> list[str]:
    """Terminate processes on Windows: taskkill then taskkill /F after timeout."""
    warnings: list[str] = []

    for pid in pids:
        try:
            result = subprocess.run(
                ["taskkill", "/PID", pid],
                capture_output=True,
                text=True,
            )
        except (OSError, FileNotFoundError) as e:
            warnings.append(f"Failed to run taskkill for process {pid}: {e}")
            continue

        if result.returncode != 0:
            # Graceful kill failed, try force kill immediately
            try:
                force_result = subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    text=True,
                )
                if force_result.returncode != 0:
                    warnings.append(
                        f"Process {pid} could not be terminated: {force_result.stderr.strip()}"
                    )
            except (OSError, FileNotFoundError) as e:
                warnings.append(f"Failed to force-kill process {pid}: {e}")
            continue

        # Wait for process to exit
        deadline = time.time() + timeout
        still_running = True
        while time.time() < deadline:
            check = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
            )
            if pid not in check.stdout:
                still_running = False
                break
            time.sleep(0.5)

        if still_running:
            try:
                force_result = subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    text=True,
                )
                if force_result.returncode != 0:
                    warnings.append(
                        f"Process {pid} could not be terminated: {force_result.stderr.strip()}"
                    )
            except (OSError, FileNotFoundError) as e:
                warnings.append(f"Failed to force-kill process {pid}: {e}")

    return warnings


def kill_kiro_processes(timeout: int = 10) -> list[str]:
    """Terminate running Kiro processes.

    Finds running Kiro processes and attempts graceful termination first.
    If processes don't exit within the timeout, force-kills them.

    Args:
        timeout: Seconds to wait after graceful termination before force-killing.
                 Defaults to 10.

    Returns:
        List of warning messages for processes that couldn't be terminated.
        Returns an empty list if no Kiro processes are running or all were
        successfully terminated.
    """
    os_name = sys.platform

    if os_name == "win32":
        pids = _find_kiro_pids_windows()
        if not pids:
            return []
        return _kill_windows(pids, timeout)
    else:
        # Unix (macOS and Linux)
        pids = _find_kiro_pids_unix()
        if not pids:
            return []
        return _kill_unix(pids, timeout)
