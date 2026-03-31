# daemon-manager

Generic daemon lifecycle manager for Claude Code plugins. Provides the `daemon` capability.

## What it does

Starts, stops, and monitors persistent background processes that survive across Claude Code sessions. Handles PID files, cross-platform IPC (Unix sockets on Linux/macOS, named pipes on Windows), and lock files to prevent race conditions.

## Architecture

```
daemon_start("my-daemon", "node", ["server.js"])
    → spawns detached process
    → writes PID to ~/.claude/daemons/my-daemon.pid
    → returns IPC address: ~/.claude/daemons/my-daemon.sock
```

MCP client processes connect to the daemon via the IPC address.

## Tools

| Tool | Description |
|------|-------------|
| `daemon_start` | Start a daemon if not running (idempotent). Returns IPC address. |
| `daemon_stop` | Stop a daemon by name. SIGTERM → wait → SIGKILL. |
| `daemon_status` | Check if daemon is running and IPC is reachable. |

## Commands

- `make test` — run tests
- `make server` — run MCP server directly

## File layout

- `server.py` — FastMCP server exposing 3 tools
- `daemon_manager.py` — core lifecycle logic
- `ipc.py` — cross-platform IPC address computation

## Environment support

Linux, macOS, Windows. Declared in marketplace as `"os": ["linux", "darwin", "windows"]`.
