"""Output formatting helpers that respect --json mode."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

_console = Console()


def get_json_mode() -> bool:
    """Check if --json flag is set in the current click context."""
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj:
        return ctx.obj.get("json", False)
    return False


def output(message: str, data: Any = None) -> None:
    """Print message (rich mode) or JSON data (json mode)."""
    if get_json_mode():
        json.dump(data if data is not None else {"message": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _console.print(message)


def error(message: str) -> None:
    """Print an error message."""
    if get_json_mode():
        json.dump({"error": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _console.print(f"[red]Error:[/red] {message}")


def table(title: str, columns: list[str], rows: list[list[str]], data: Any = None) -> None:
    """Print a rich table or JSON data."""
    if get_json_mode():
        if data is not None:
            json.dump(data, sys.stdout)
        else:
            json.dump({"columns": columns, "rows": rows}, sys.stdout)
        sys.stdout.write("\n")
    else:
        t = Table(title=title)
        for col in columns:
            t.add_column(col)
        for row in rows:
            t.add_row(*row)
        _console.print(t)


def warn(message: str) -> None:
    """Print a warning message."""
    if get_json_mode():
        json.dump({"warning": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _console.print(f"[yellow]{message}[/yellow]")


def success(message: str) -> None:
    """Print a success message."""
    if get_json_mode():
        json.dump({"status": "ok", "message": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _console.print(f"[green]{message}[/green]")
