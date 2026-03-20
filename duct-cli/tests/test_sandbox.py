"""Tests for duct.sandbox module."""

import json
from pathlib import Path

from duct.config import SandboxConfig
from duct.sandbox import build_settings, write_settings


class TestBuildSettings:
    def test_defaults(self):
        result = build_settings(SandboxConfig())

        assert result["sandbox"]["enabled"] is True
        assert result["sandbox"]["autoAllowBashIfSandboxed"] is True
        assert "." in result["sandbox"]["filesystem"]["allowWrite"]
        assert "~/.m2" in result["sandbox"]["filesystem"]["allowWrite"]
        assert "~/.ssh" in result["sandbox"]["filesystem"]["denyRead"]
        # No network key when allowedDomains is empty.
        assert "network" not in result["sandbox"]

    def test_custom_deny_read(self):
        cfg = SandboxConfig(deny_read=("~/.ssh", "~/.secrets"))
        result = build_settings(cfg)

        assert result["sandbox"]["filesystem"]["denyRead"] == ["~/.ssh", "~/.secrets"]

    def test_with_domains(self):
        cfg = SandboxConfig(allowed_domains=("api.example.com", "cdn.example.com"))
        result = build_settings(cfg)

        assert result["sandbox"]["network"]["allowedDomains"] == [
            "api.example.com",
            "cdn.example.com",
        ]


class TestWriteSettings:
    def test_creates_file(self, tmp_path: Path):
        path = write_settings(tmp_path, SandboxConfig())

        assert path == tmp_path / ".claude" / "settings.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["sandbox"]["enabled"] is True
        assert "." in data["sandbox"]["filesystem"]["allowWrite"]

    def test_merges_existing(self, tmp_path: Path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"env": {"FOO": "bar"}, "sandbox": {"enabled": False}}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        write_settings(tmp_path, SandboxConfig())

        data = json.loads((claude_dir / "settings.json").read_text())
        # Sandbox key replaced with new config.
        assert data["sandbox"]["enabled"] is True
        # Other keys preserved.
        assert data["env"] == {"FOO": "bar"}

    def test_idempotent(self, tmp_path: Path):
        write_settings(tmp_path, SandboxConfig())
        first = (tmp_path / ".claude" / "settings.json").read_text()

        write_settings(tmp_path, SandboxConfig())
        second = (tmp_path / ".claude" / "settings.json").read_text()

        assert first == second
