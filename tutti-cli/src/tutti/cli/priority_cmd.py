"""tutti priority -- view and edit PRIORITY.md."""

from __future__ import annotations

from pathlib import Path

import click

from tutti.cli.output import error, output, success, warn
from tutti.cli.resolve import complete_ticket_key, resolve_root
from tutti.config import ConfigError
from tutti.markdown import TICKET_KEY_PATTERN


def _read_priority_keys(priority_file: Path) -> list[str]:
    """Parse PRIORITY.md and return list of ticket keys in order."""
    if not priority_file.exists():
        return []
    keys: list[str] = []
    for line in priority_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("- "):
            m = TICKET_KEY_PATTERN.search(line)
            if m:
                keys.append(m.group(0))
    return keys


def _write_priority(priority_file: Path, keys: list[str]) -> None:
    """Write PRIORITY.md with the given keys."""
    lines = ["# Priority", ""]
    for key in keys:
        lines.append(f"- {key}")
    lines.append("")
    priority_file.write_text("\n".join(lines), encoding="utf-8")


@click.group(invoke_without_command=True)
@click.pass_context
def priority(ctx: click.Context) -> None:
    """View or edit the priority list."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        root = resolve_root(ctx)
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
@click.argument("keys", nargs=-1, required=True, shell_complete=complete_ticket_key)
@click.pass_context
def priority_set(ctx: click.Context, keys: tuple[str, ...]) -> None:
    """Set the priority list. Pass ticket keys in priority order."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    _write_priority(root / "PRIORITY.md", list(keys))
    success(f"Priority set: {', '.join(keys)}")


@priority.command("add")
@click.argument("key", shell_complete=complete_ticket_key)
@click.option(
    "--position", "-p", type=int, default=None,
    help="Insert at position (1-based). Appends if omitted.",
)
@click.pass_context
def priority_add(ctx: click.Context, key: str, position: int | None) -> None:
    """Add a ticket to the priority list."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    priority_file = root / "PRIORITY.md"
    keys = _read_priority_keys(priority_file)

    if key in keys:
        warn(f"{key} is already in the priority list (position {keys.index(key) + 1}).")
        return

    if position is not None:
        idx = max(0, min(position - 1, len(keys)))
        keys.insert(idx, key)
    else:
        keys.append(key)

    _write_priority(priority_file, keys)
    pos = keys.index(key) + 1
    success(f"Added {key} at position {pos}. Priority: {', '.join(keys)}")


@priority.command("remove")
@click.argument("key", shell_complete=complete_ticket_key)
@click.pass_context
def priority_remove(ctx: click.Context, key: str) -> None:
    """Remove a ticket from the priority list."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    priority_file = root / "PRIORITY.md"
    keys = _read_priority_keys(priority_file)

    if key not in keys:
        warn(f"{key} is not in the priority list.")
        return

    keys.remove(key)
    _write_priority(priority_file, keys)
    success(f"Removed {key}. Priority: {', '.join(keys) if keys else '(empty)'}")
