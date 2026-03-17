"""tutti ticket -- list and show tracked tickets."""

from __future__ import annotations

import re
from pathlib import Path

import click

from tutti.cli.output import error, output, table
from tutti.config import ConfigError, find_workspace_root
from tutti.markdown import extract_table, parse_frontmatter
from tutti.workspace import enumerate_ticket_dirs, resolve_ticket_dir


def _resolve_root(ctx: click.Context) -> Path:
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


def _parse_ticket_md(content: str) -> dict[str, str]:
    """Extract metadata from a TICKET.md file.

    Returns a dict with keys: key, summary, status, category, plus
    any other fields found in the metadata table.
    """
    _meta, body = parse_frontmatter(content)
    info: dict[str, str] = {}

    # Extract key and summary from the first H1 heading: "# KEY: Summary"
    for line in body.splitlines():
        line = line.strip()
        m = re.match(r"^#\s+([A-Z]+-\d+):\s+(.+)$", line)
        if m:
            info["key"] = m.group(1)
            info["summary"] = m.group(2)
            break

    # Extract fields from the metadata table (Field | Value columns).
    rows = extract_table(body)
    for row in rows:
        field_name = row.get("Field", "").strip()
        value = row.get("Value", "").strip()
        if field_name and value:
            info[field_name.lower()] = value

    return info


@click.group()
@click.pass_context
def ticket(ctx: click.Context) -> None:
    """List and inspect tracked tickets."""
    pass


@ticket.command("list")
@click.pass_context
def ticket_list(ctx: click.Context) -> None:
    """List all tracked tickets."""
    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    tickets = enumerate_ticket_dirs(root)
    if not tickets:
        output("No tracked tickets.", data=[])
        return

    columns = ["Key", "Summary", "Status", "Category"]
    rows: list[list[str]] = []
    json_data: list[dict[str, str]] = []

    for key, path in tickets:
        ticket_md = path / "orchestrator" / "TICKET.md"
        info: dict[str, str] = {}
        if ticket_md.exists():
            try:
                info = _parse_ticket_md(ticket_md.read_text(encoding="utf-8"))
            except Exception:
                pass

        row_key = info.get("key", key)
        summary = info.get("summary", "")
        status = info.get("status", "")
        category = info.get("category", "")

        rows.append([row_key, summary, status, category])
        json_data.append({
            "key": row_key,
            "summary": summary,
            "status": status,
            "category": category,
            "path": str(path),
        })

    table("Tracked Tickets", columns, rows, data=json_data)


@ticket.command("show")
@click.argument("key")
@click.pass_context
def ticket_show(ctx: click.Context, key: str) -> None:
    """Show ticket details and artifact inventory."""
    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if ticket_dir is None:
        error(f"Ticket {key} not found.")
        ctx.exit(1)
        return

    orch_dir = ticket_dir / "orchestrator"
    ticket_md = orch_dir / "TICKET.md"

    # Read TICKET.md content.
    ticket_content = ""
    if ticket_md.exists():
        ticket_content = ticket_md.read_text(encoding="utf-8")

    # Build artifact inventory (files in orchestrator/).
    artifacts: list[str] = []
    if orch_dir.is_dir():
        for f in sorted(orch_dir.iterdir()):
            if f.is_file():
                artifacts.append(f.name)

    # Identify repo worktrees (dirs in ticket_dir that are not orchestrator/).
    repos: list[str] = []
    for child in sorted(ticket_dir.iterdir()):
        if child.is_dir() and child.name != "orchestrator":
            repos.append(child.name)

    json_data = {
        "key": key,
        "path": str(ticket_dir),
        "ticket_md": ticket_content,
        "artifacts": artifacts,
        "repos": repos,
    }

    if ctx.obj and ctx.obj.get("json"):
        output("", data=json_data)
    else:
        if ticket_content:
            output(ticket_content)
        else:
            output(f"[dim]No TICKET.md found for {key}.[/dim]")

        if artifacts:
            output("\n[bold]Artifacts:[/bold]")
            for a in artifacts:
                output(f"  {a}")
        else:
            output("\n[dim]No artifacts.[/dim]")

        if repos:
            output("\n[bold]Repo worktrees:[/bold]")
            for r in repos:
                output(f"  {r}")
