"""Cross-platform IPC address computation for daemon-manager."""

import platform
from pathlib import Path


def get_daemons_dir() -> Path:
    """Return the daemons directory, creating it if needed."""
    d = Path.home() / ".claude" / "daemons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_ipc_address(daemon_name: str) -> str:
    r"""Return the platform-appropriate IPC address for a daemon.

    Linux/macOS: Unix domain socket path (~/.claude/daemons/{name}.sock)
    Windows: Named pipe (\\.\pipe\claude-daemon-{name})
    """
    if platform.system() == "Windows":
        return f"\\\\.\\pipe\\claude-daemon-{daemon_name}"
    return str(get_daemons_dir() / f"{daemon_name}.sock")


def get_pid_path(daemon_name: str) -> Path:
    """Return the PID file path for a daemon."""
    return get_daemons_dir() / f"{daemon_name}.pid"


def get_lock_path(daemon_name: str) -> Path:
    """Return the lock file path for a daemon."""
    return get_daemons_dir() / f"{daemon_name}.lock"
