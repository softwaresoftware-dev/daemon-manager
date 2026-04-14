"""Core daemon lifecycle logic — start, stop, status.

Handles PID files, process spawning, lock files, and cross-platform differences.
"""

import json
import os
import platform
import signal
import socket
import subprocess
import time
from pathlib import Path

from ipc import get_config_path, get_daemons_dir, get_ipc_address, get_lock_path, get_pid_path

IS_WINDOWS = platform.system() == "Windows"


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        if IS_WINDOWS:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def _is_ipc_reachable(address: str) -> bool:
    """Check if the IPC endpoint is accepting connections."""
    try:
        if IS_WINDOWS:
            # Named pipe check — try to open and immediately close
            import ctypes
            handle = ctypes.windll.kernel32.CreateFileW(
                address, 0x80000000, 0, None, 3, 0, None  # GENERIC_READ, OPEN_EXISTING
            )
            if handle != -1:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(address)
            sock.close()
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _read_pid(daemon_name: str) -> int | None:
    """Read PID from file, return None if missing or invalid."""
    pid_path = get_pid_path(daemon_name)
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text().strip())
        return pid if pid > 0 else None
    except (ValueError, OSError):
        return None


def _write_pid(daemon_name: str, pid: int) -> None:
    """Write PID to file."""
    get_pid_path(daemon_name).write_text(str(pid))


def _cleanup(daemon_name: str) -> None:
    """Remove PID file and IPC socket file."""
    pid_path = get_pid_path(daemon_name)
    if pid_path.exists():
        pid_path.unlink(missing_ok=True)

    address = get_ipc_address(daemon_name)
    if not IS_WINDOWS:
        sock_path = Path(address)
        if sock_path.exists():
            sock_path.unlink(missing_ok=True)


def _acquire_lock(daemon_name: str):
    """Acquire a file lock to prevent concurrent daemon starts.

    Returns a file handle that must be passed to _release_lock.
    """
    lock_path = get_lock_path(daemon_name)
    f = open(lock_path, "w")
    if IS_WINDOWS:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    return f


def _release_lock(lock_handle) -> None:
    """Release the file lock."""
    if lock_handle:
        try:
            if IS_WINDOWS:
                import msvcrt
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


def daemon_start(
    daemon_name: str,
    command: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    """Start a daemon if not already running. Idempotent.

    Returns dict with 'ipc_address', 'pid', and 'status' ('already_running' or 'started').
    """
    args = args or []
    ipc_address = get_ipc_address(daemon_name)

    # Fast path: check if already running
    pid = _read_pid(daemon_name)
    if pid and _is_process_alive(pid) and _is_ipc_reachable(ipc_address):
        return {
            "daemon_name": daemon_name,
            "ipc_address": ipc_address,
            "pid": pid,
            "status": "already_running",
        }

    # Acquire lock to prevent race between concurrent sessions
    lock = _acquire_lock(daemon_name)
    try:
        # Re-check after acquiring lock (another session may have started it)
        pid = _read_pid(daemon_name)
        if pid and _is_process_alive(pid) and _is_ipc_reachable(ipc_address):
            return {
                "daemon_name": daemon_name,
                "ipc_address": ipc_address,
                "pid": pid,
                "status": "already_running",
            }

        # Clean up stale state
        _cleanup(daemon_name)

        # Build environment
        spawn_env = {**os.environ, **(env or {})}
        spawn_env["DAEMON_IPC_ADDRESS"] = ipc_address

        # Ensure daemons dir exists
        get_daemons_dir()

        # Spawn detached process
        kwargs = {
            "env": spawn_env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if cwd:
            kwargs["cwd"] = cwd

        if IS_WINDOWS:
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen([command, *args], **kwargs)
        _write_pid(daemon_name, proc.pid)

        # Persist config so setup/list can reference it later
        config = {"command": command, "args": args, "cwd": cwd}
        if env:
            config["env"] = env
        get_config_path(daemon_name).write_text(json.dumps(config))

        # Wait for IPC to become available (up to 5 seconds)
        for _ in range(50):
            time.sleep(0.1)
            if _is_ipc_reachable(ipc_address):
                return {
                    "daemon_name": daemon_name,
                    "ipc_address": ipc_address,
                    "pid": proc.pid,
                    "status": "started",
                }

        # Process started but IPC not reachable — check if it crashed
        if not _is_process_alive(proc.pid):
            _cleanup(daemon_name)
            return {
                "daemon_name": daemon_name,
                "error": "Daemon process exited immediately after start",
                "status": "failed",
            }

        return {
            "daemon_name": daemon_name,
            "ipc_address": ipc_address,
            "pid": proc.pid,
            "status": "started",
            "warning": "IPC not reachable yet — daemon may still be initializing",
        }
    finally:
        _release_lock(lock)


def daemon_stop(daemon_name: str) -> dict:
    """Stop a running daemon. Clean up PID file and socket."""
    pid = _read_pid(daemon_name)
    if not pid:
        _cleanup(daemon_name)
        return {"daemon_name": daemon_name, "status": "not_running"}

    if not _is_process_alive(pid):
        _cleanup(daemon_name)
        return {"daemon_name": daemon_name, "status": "not_running", "note": "stale PID cleaned up"}

    # Send SIGTERM and wait
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5)
        else:
            os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):
            time.sleep(0.1)
            # Reap zombie if we're the parent
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
            if not _is_process_alive(pid):
                break
        else:
            # Force kill if still alive
            if not IS_WINDOWS:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
    except (ProcessLookupError, OSError):
        pass

    _cleanup(daemon_name)
    return {"daemon_name": daemon_name, "pid": pid, "status": "stopped"}


def daemon_status(daemon_name: str) -> dict:
    """Check the status of a daemon."""
    ipc_address = get_ipc_address(daemon_name)
    pid = _read_pid(daemon_name)

    if not pid:
        return {
            "daemon_name": daemon_name,
            "running": False,
            "ipc_address": ipc_address,
        }

    alive = _is_process_alive(pid)
    reachable = _is_ipc_reachable(ipc_address) if alive else False

    return {
        "daemon_name": daemon_name,
        "running": alive,
        "ipc_reachable": reachable,
        "pid": pid,
        "ipc_address": ipc_address,
    }


def _get_systemd_service_path(daemon_name: str) -> Path | None:
    """Return the systemd user service path if it exists."""
    if IS_WINDOWS:
        return None
    path = Path.home() / ".config" / "systemd" / "user" / f"{daemon_name}.service"
    return path if path.exists() else None


def _get_launchd_plist_path(daemon_name: str) -> Path | None:
    """Return the launchd plist path if it exists."""
    if platform.system() != "Darwin":
        return None
    path = Path.home() / "Library" / "LaunchAgents" / f"com.claude.daemon.{daemon_name}.plist"
    return path if path.exists() else None


def _has_windows_scheduled_task(daemon_name: str) -> bool:
    """Check if a Windows Scheduled Task exists for this daemon."""
    if not IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", f"claude-daemon-{daemon_name}"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def daemon_list() -> dict:
    """List all known daemons with their status and service configuration.

    Scans ~/.claude/daemons/ for PID files and config files to discover
    daemons. Cross-references with systemd/launchd to detect which ones
    have auto-start configured.
    """
    daemons_dir = get_daemons_dir()
    seen = set()
    results = []

    # Find daemons from PID files and config files
    for f in daemons_dir.iterdir():
        if f.suffix in (".pid", ".json"):
            name = f.stem
            if name not in seen:
                seen.add(name)

    for name in sorted(seen):
        ipc_address = get_ipc_address(name)
        pid = _read_pid(name)
        alive = _is_process_alive(pid) if pid else False
        reachable = _is_ipc_reachable(ipc_address) if alive else False

        # Load saved config
        config_path = get_config_path(name)
        config = None
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Check for OS service manager
        has_service = False
        service_type = None
        if IS_WINDOWS:
            if _has_windows_scheduled_task(name):
                has_service = True
                service_type = "task_scheduler"
        elif platform.system() == "Darwin":
            if _get_launchd_plist_path(name):
                has_service = True
                service_type = "launchd"
        else:
            if _get_systemd_service_path(name):
                has_service = True
                service_type = "systemd"

        entry = {
            "daemon_name": name,
            "running": alive,
            "ipc_reachable": reachable,
            "pid": pid,
            "has_autostart": has_service,
            "service_type": service_type,
        }
        if config:
            entry["config"] = config

        results.append(entry)

    return {"daemons": results}
