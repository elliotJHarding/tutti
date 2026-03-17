"""tutti priority -- view and edit PRIORITY.md."""

from __future__ import annotations

from pathlib import Path

import click

from tutti.cli.output import error, output, success
from tutti.config import ConfigError, find_workspace_root


def _resolve_root(ctx: click.Context) -> Path:
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


@click.group(invoke_without_command=True)
@click.pass_context
def priority(ctx: click.Context) -> None:
    """View or edit the priority list."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    priority_file = root / "PRIORITY.md"
    if not priority_file.exists():
        output("No PRIORITY.md found. Run 'tutti init' first.")
        return

    content = priority_file.read_text()
    output(content, data={"content": content})


@priority.command("set")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def priority_set(ctx: click.Context, keys: tuple[str, ...]) -> None:
    """Set the priority list. Pass ticket keys in priority order."""
    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    lines = ["# Priority", ""]
    for key in keys:
        lines.append(f"- {key}")
    lines.append("")

    content = "\n".join(lines)
    priority_file = root / "PRIORITY.md"
    priority_file.write_text(content, encoding="utf-8")
    success(f"Priority set: {', '.join(keys)}")
