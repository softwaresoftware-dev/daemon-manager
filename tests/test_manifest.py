"""Tests for plugin manifest — required fields and version consistency."""

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def plugin_json():
    return _read_json(os.path.join(ROOT, ".claude-plugin", "plugin.json"))


@pytest.fixture
def pyproject():
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def test_required_fields(plugin_json):
    for field in ["name", "description", "version", "author", "keywords"]:
        assert field in plugin_json, f"Missing required field: {field}"


def test_name(plugin_json):
    assert plugin_json["name"] == "daemon-manager"


def test_semver(plugin_json):
    assert re.match(r"^\d+\.\d+\.\d+$", plugin_json["version"])


def test_version_matches_pyproject(plugin_json, pyproject):
    assert plugin_json["version"] == pyproject["project"]["version"]


def test_mcp_server_config(plugin_json):
    assert "mcpServers" in plugin_json
    assert "daemon-manager" in plugin_json["mcpServers"]
    server = plugin_json["mcpServers"]["daemon-manager"]
    assert server["command"] == "uv"
    assert server["args"][:3] == ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}"]
    assert "server.py" in server["args"]
