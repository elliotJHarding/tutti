"""Configuration loading, saving, and workspace discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

import yaml

from tutti.exceptions import AuthError, ConfigError

TrustLevel = Literal["auto", "propose", "deny"]

_DEFAULT_JQL = "assignee = currentUser() AND status != Done ORDER BY updated DESC"
_CONFIG_FILENAME = "config.yaml"


@dataclass(frozen=True)
class TrustConfig:
    """Per-action trust levels controlling what tutti may do autonomously."""

    write_artifact: TrustLevel = "auto"
    git_commit: TrustLevel = "propose"
    git_push: TrustLevel = "propose"
    jira_comment: TrustLevel = "propose"
    jira_transition: TrustLevel = "deny"
    pr_create: TrustLevel = "propose"
    pr_merge: TrustLevel = "deny"
    time_log: TrustLevel = "propose"


@dataclass(frozen=True)
class SyncIntervals:
    """Sync polling intervals in seconds."""

    jira: int = 10800
    github: int = 10800
    sessions: int = 900
    workspace: int = 1800
    ci: int = 10800


@dataclass(frozen=True)
class WorkspaceConfig:
    """Immutable workspace configuration."""

    root: Path = field(default_factory=lambda: Path.home() / "workspace" / "tutti")
    jira_jql: str = _DEFAULT_JQL
    jira_domain: str = ""
    repo_paths: list[Path] = field(
        default_factory=lambda: [Path.home() / "workspace", Path.home() / "projects"]
    )
    trust: TrustConfig = field(default_factory=TrustConfig)
    sync_intervals: SyncIntervals = field(default_factory=SyncIntervals)


# ---------------------------------------------------------------------------
# YAML camelCase <-> Python snake_case mapping
# ---------------------------------------------------------------------------

_TRUST_YAML_TO_PY = {
    "writeArtifact": "write_artifact",
    "gitCommit": "git_commit",
    "gitPush": "git_push",
    "jiraComment": "jira_comment",
    "jiraTransition": "jira_transition",
    "prCreate": "pr_create",
    "prMerge": "pr_merge",
    "timeLog": "time_log",
}
_TRUST_PY_TO_YAML = {v: k for k, v in _TRUST_YAML_TO_PY.items()}


def _parse_trust(raw: dict[str, Any]) -> TrustConfig:
    kwargs: dict[str, Any] = {}
    for yaml_key, py_key in _TRUST_YAML_TO_PY.items():
        if yaml_key in raw:
            kwargs[py_key] = raw[yaml_key]
    return TrustConfig(**kwargs)


def _trust_to_dict(trust: TrustConfig) -> dict[str, str]:
    result: dict[str, str] = {}
    for f in fields(trust):
        yaml_key = _TRUST_PY_TO_YAML[f.name]
        result[yaml_key] = getattr(trust, f.name)
    return result


def _parse_sync_intervals(raw: dict[str, Any]) -> SyncIntervals:
    known = {f.name for f in fields(SyncIntervals)}
    kwargs = {k: v for k, v in raw.items() if k in known}
    return SyncIntervals(**kwargs)


def _sync_intervals_to_dict(intervals: SyncIntervals) -> dict[str, int]:
    return {f.name: getattr(intervals, f.name) for f in fields(intervals)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(root: Path) -> WorkspaceConfig:
    """Load configuration from *root*/config.yaml, falling back to defaults."""
    config_path = root / _CONFIG_FILENAME
    if not config_path.exists():
        return WorkspaceConfig(root=root)

    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    workspace_section = raw.get("workspace", {})
    jira_section = raw.get("jira", {})

    ws_root_str = workspace_section.get("root")
    ws_root = Path(ws_root_str).expanduser() if ws_root_str else root

    repo_paths_raw = raw.get("repoPaths")
    if repo_paths_raw is not None:
        repo_paths = [Path(p).expanduser() for p in repo_paths_raw]
    else:
        repo_paths = WorkspaceConfig().repo_paths

    trust = _parse_trust(raw.get("trust", {}))
    sync_intervals = _parse_sync_intervals(raw.get("syncIntervals", {}))

    return WorkspaceConfig(
        root=ws_root,
        jira_jql=jira_section.get("jql", _DEFAULT_JQL),
        jira_domain=jira_section.get("domain", ""),
        repo_paths=repo_paths,
        trust=trust,
        sync_intervals=sync_intervals,
    )


def save_config(config: WorkspaceConfig, root: Path) -> None:
    """Write *config* as config.yaml inside *root*."""
    root.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "workspace": {
            "root": str(config.root),
        },
        "jira": {
            "domain": config.jira_domain,
            "jql": config.jira_jql,
        },
        "repoPaths": [str(p) for p in config.repo_paths],
        "trust": _trust_to_dict(config.trust),
        "syncIntervals": _sync_intervals_to_dict(config.sync_intervals),
    }
    config_path = root / _CONFIG_FILENAME
    config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def find_workspace_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) looking for config.yaml.

    Returns the directory containing config.yaml, or raises ConfigError.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / _CONFIG_FILENAME).exists():
            return current
        parent = current.parent
        if parent == current:
            raise ConfigError(
                f"No {_CONFIG_FILENAME} found in {start or Path.cwd()} or any parent directory"
            )
        current = parent


# ---------------------------------------------------------------------------
# Auth helpers — read credentials from environment variables
# ---------------------------------------------------------------------------


def jira_email() -> str:
    """Return JIRA_EMAIL from the environment, or raise AuthError."""
    value = os.environ.get("JIRA_EMAIL")
    if not value:
        raise AuthError("JIRA_EMAIL environment variable is not set")
    return value


def jira_token() -> str:
    """Return JIRA_TOKEN from the environment, or raise AuthError."""
    value = os.environ.get("JIRA_TOKEN")
    if not value:
        raise AuthError("JIRA_TOKEN environment variable is not set")
    return value


def gh_token() -> str:
    """Return GH_TOKEN (or GITHUB_TOKEN) from the environment, or raise AuthError."""
    value = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not value:
        raise AuthError("GH_TOKEN environment variable is not set")
    return value
