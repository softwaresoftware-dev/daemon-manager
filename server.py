"""MCP server for daemon-manager — generic daemon lifecycle management.

Implements the daemon capability contract:
  daemon_start(daemon_name, command, ...) → IPC address (idempotent)
  daemon_stop(daemon_name) → confirmation
  daemon_status(daemon_name) → running state, PID, IPC address
"""

from mcp.server.fastmcp import FastMCP

import daemon_manager

mcp = FastMCP("daemon-manager")


@mcp.tool()
def daemon_start(
    daemon_name: str,
    command: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    """Start a daemon process if not already running. Idempotent.

    If the daemon is already running and its IPC endpoint is reachable,
    returns the existing IPC address without restarting.

    Args:
        daemon_name: Unique name for this daemon instance.
        command: Command to execute (e.g. "node", "python").
        args: Command arguments (e.g. ["server/daemon.js"]).
        cwd: Working directory for the daemon process.
        env: Additional environment variables to set.

    Returns:
        Dict with daemon_name, ipc_address, pid, and status
        ('already_running', 'started', or 'failed').
    """
    return daemon_manager.daemon_start(daemon_name, command, args, cwd, env)


@mcp.tool()
def daemon_stop(daemon_name: str) -> dict:
    """Stop a running daemon and clean up its PID file and socket.

    Args:
        daemon_name: Name of the daemon to stop.

    Returns:
        Dict with daemon_name, status ('stopped' or 'not_running').
    """
    return daemon_manager.daemon_stop(daemon_name)


@mcp.tool()
def daemon_status(daemon_name: str) -> dict:
    """Check whether a daemon is running and if its IPC endpoint is reachable.

    Args:
        daemon_name: Name of the daemon to check.

    Returns:
        Dict with daemon_name, running (bool), ipc_reachable (bool),
        pid, and ipc_address.
    """
    return daemon_manager.daemon_status(daemon_name)


if __name__ == "__main__":
    mcp.run()
