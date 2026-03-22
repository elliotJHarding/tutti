"""Shared CLI utility: workspace root resolution and completion helpers."""

from __future__ import annotations

from pathlib import Path

import click
from click.shell_completion import CompletionItem

from duct.config import find_workspace_root


def resolve_root(ctx: click.Context) -> Path:
    """Determine workspace root from context or by walking up the filesystem."""
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


def detect_current_ticket(root: Path) -> str | None:
    """Return ticket key if cwd is inside a ticket directory under root."""
    from duct.workspace import _is_ticket_dir, _key_from_dirname

    cwd = Path.cwd().resolve()
    try:
        rel = cwd.relative_to(root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    candidate = root / parts[0]
    key = _key_from_dirname(parts[0])
    if key and _is_ticket_dir(candidate):
        return key
    return None


def workspace_option():
    """Reusable --workspace / -w / --ws Click option decorator."""
    return click.option(
        "--workspace", "-w", "--ws",
        "workspace_key",
        metavar="KEY",
        default=None,
        shell_complete=complete_ticket_key,
        help="Target a specific ticket workspace.",
    )


def resolve_ticket_key(ctx: click.Context, explicit_key: str | None) -> str | None:
    """Resolve ticket key: explicit arg > CWD detection > None.

    None means 'no specific ticket' — caller decides whether to operate on
    all workspaces or raise an error.
    """
    if explicit_key:
        return explicit_key.upper()
    try:
        root = resolve_root(ctx)
    except Exception:
        return None
    return detect_current_ticket(root)


def complete_ticket_key(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Shell completion callback that suggests known ticket keys."""
    try:
        root = resolve_root(ctx)
    except Exception:
        return []
    from duct.workspace import enumerate_ticket_dirs

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
    from duct.config import load_config
    from duct.cli.workspace_cmd import discover_repos

    cfg = load_config(root)
    names = [name for name, _ in discover_repos(cfg)]
    return [
        CompletionItem(n)
        for n in names
        if n.lower().startswith(incomplete.lower())
    ]
