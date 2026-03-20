"""Shared CLI utility: workspace root resolution and completion helpers."""

from __future__ import annotations

from pathlib import Path

import click
from click.shell_completion import CompletionItem

from tutti.config import find_workspace_root


def resolve_root(ctx: click.Context) -> Path:
    """Determine workspace root from context or by walking up the filesystem."""
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


def complete_ticket_key(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Shell completion callback that suggests known ticket keys."""
    try:
        root = resolve_root(ctx)
    except Exception:
        return []
    from tutti.workspace import enumerate_ticket_dirs

    keys = [key for key, _ in enumerate_ticket_dirs(root)]
    return [
        CompletionItem(k)
        for k in keys
        if k.lower().startswith(incomplete.lower())
    ]


def complete_repo_name(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Shell completion callback that suggests discovered repository names."""
    try:
        root = resolve_root(ctx)
    except Exception:
        return []
    from tutti.config import load_config
    from tutti.cli.workspace_cmd import discover_repos

    cfg = load_config(root)
    names = [name for name, _ in discover_repos(cfg)]
    return [
        CompletionItem(n)
        for n in names
        if n.lower().startswith(incomplete.lower())
    ]
