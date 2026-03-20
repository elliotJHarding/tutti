"""Sandbox configuration for Claude Code sessions."""

from __future__ import annotations

import json
from pathlib import Path

from duct.config import SandboxConfig


def build_settings(config: SandboxConfig) -> dict:
    """Produce a Claude Code settings dict from sandbox configuration."""
    filesystem: dict[str, list[str]] = {}
    if config.allow_write:
        filesystem["allowWrite"] = list(config.allow_write)
    if config.deny_read:
        filesystem["denyRead"] = list(config.deny_read)

    sandbox: dict = {
        "enabled": config.enabled,
        "autoAllowBashIfSandboxed": config.auto_allow_bash,
        "filesystem": filesystem,
    }

    if config.allowed_domains:
        sandbox["network"] = {"allowedDomains": list(config.allowed_domains)}

    return {"sandbox": sandbox}


def write_settings(target_dir: Path, config: SandboxConfig) -> Path:
    """Write sandbox config into ``{target_dir}/.claude/settings.json``.

    If the file already exists, only the ``sandbox`` key is replaced;
    other keys (e.g. ``env``) are preserved.  Returns the path written.
    """
    claude_dir = target_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    new_settings = build_settings(config)
    existing["sandbox"] = new_settings["sandbox"]

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    return settings_path
