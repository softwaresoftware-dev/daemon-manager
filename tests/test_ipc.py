"""Tests for ipc.py — cross-platform IPC address computation."""

import os
import platform
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

import ipc


def test_get_daemons_dir(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = ipc.get_daemons_dir()
    assert d.exists()
    assert d == tmp_path / ".claude" / "daemons"


def test_get_ipc_address_unix(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    addr = ipc.get_ipc_address("test-daemon")
    assert addr.endswith("test-daemon.sock")
    assert ".claude/daemons/" in addr


def test_get_ipc_address_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    addr = ipc.get_ipc_address("test-daemon")
    assert addr == "\\\\.\\pipe\\claude-daemon-test-daemon"


def test_get_pid_path():
    p = ipc.get_pid_path("test-daemon")
    assert p.name == "test-daemon.pid"
    assert ".claude/daemons" in str(p)


def test_get_lock_path():
    p = ipc.get_lock_path("test-daemon")
    assert p.name == "test-daemon.lock"
    assert ".claude/daemons" in str(p)
