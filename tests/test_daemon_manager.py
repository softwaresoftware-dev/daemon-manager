"""Tests for daemon_manager.py — core lifecycle logic."""

import os
import signal
import socket
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

import daemon_manager
import ipc


@pytest.fixture
def daemons_dir(tmp_path, monkeypatch):
    """Redirect daemons directory to tmp."""
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    import ipc as ipc_mod
    # Re-derive paths after monkeypatching home
    d = tmp_path / ".claude" / "daemons"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def unix_echo_server(daemons_dir):
    """Start a Unix socket server that accepts connections (simulates a daemon IPC)."""
    sock_path = str(daemons_dir / "test-daemon.sock")
    if os.path.exists(sock_path):
        os.unlink(sock_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    server.settimeout(5)

    def accept_loop():
        try:
            while True:
                conn, _ = server.accept()
                conn.close()
        except (OSError, socket.timeout):
            pass

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()

    yield sock_path

    server.close()
    if os.path.exists(sock_path):
        os.unlink(sock_path)


def test_is_process_alive_self():
    assert daemon_manager._is_process_alive(os.getpid()) is True


def test_is_process_alive_nonexistent():
    assert daemon_manager._is_process_alive(999999999) is False


def test_read_write_pid(daemons_dir):
    daemon_manager._write_pid("test-daemon", 12345)
    assert daemon_manager._read_pid("test-daemon") == 12345


def test_read_pid_missing(daemons_dir):
    assert daemon_manager._read_pid("nonexistent") is None


def test_cleanup(daemons_dir):
    # Create PID file and socket file
    pid_path = ipc.get_pid_path("test-daemon")
    pid_path.write_text("12345")
    sock_path = daemons_dir / "test-daemon.sock"
    sock_path.touch()

    daemon_manager._cleanup("test-daemon")
    assert not pid_path.exists()
    assert not sock_path.exists()


def test_is_ipc_reachable_unix(unix_echo_server):
    assert daemon_manager._is_ipc_reachable(unix_echo_server) is True


def test_is_ipc_not_reachable():
    assert daemon_manager._is_ipc_reachable("/tmp/nonexistent-socket-12345.sock") is False


def test_daemon_start_spawns_process(daemons_dir, monkeypatch):
    """Start a simple sleep process as a daemon."""
    result = daemon_manager.daemon_start(
        "test-sleep",
        "sleep",
        args=["300"],
    )
    assert result["status"] in ("started", "already_running")
    assert result["pid"] > 0

    # Verify PID file was written
    pid = daemon_manager._read_pid("test-sleep")
    assert pid == result["pid"]
    assert daemon_manager._is_process_alive(pid)

    # Clean up
    daemon_manager.daemon_stop("test-sleep")


def test_daemon_start_idempotent(daemons_dir, unix_echo_server):
    """If daemon is already running with reachable IPC, return existing info."""
    pid = os.getpid()
    daemon_manager._write_pid("test-daemon", pid)

    result = daemon_manager.daemon_start(
        "test-daemon",
        "sleep",
        args=["300"],
    )
    assert result["status"] == "already_running"
    assert result["pid"] == pid


def test_daemon_stop_not_running(daemons_dir):
    result = daemon_manager.daemon_stop("nonexistent")
    assert result["status"] == "not_running"


def test_daemon_stop_kills_process(daemons_dir):
    """Start a process and verify stop kills it."""
    result = daemon_manager.daemon_start("test-stop", "sleep", args=["300"])
    pid = result["pid"]
    assert daemon_manager._is_process_alive(pid)

    stop_result = daemon_manager.daemon_stop("test-stop")
    assert stop_result["status"] == "stopped"
    # daemon_stop waits up to 5s internally, process should be dead by now
    time.sleep(0.5)
    assert not daemon_manager._is_process_alive(pid)


def test_daemon_status_not_running(daemons_dir):
    result = daemon_manager.daemon_status("nonexistent")
    assert result["running"] is False


def test_daemon_status_running(daemons_dir, unix_echo_server):
    """Status should report running when PID is alive and IPC reachable."""
    daemon_manager._write_pid("test-daemon", os.getpid())

    result = daemon_manager.daemon_status("test-daemon")
    assert result["running"] is True
    assert result["ipc_reachable"] is True
    assert result["pid"] == os.getpid()
