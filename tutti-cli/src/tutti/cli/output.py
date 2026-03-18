"""Output formatting helpers that respect --json mode."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

import click

_console = None


def _get_console():
    global _console
    if _console is None:
        from rich.console import Console

        _console = Console()
    return _console


@dataclass
class Col:
    """Per-column configuration for table()."""

    header: str
    justify: Literal["left", "center", "right"] = "left"
    style: str = ""
    max_width: int | None = None
    no_wrap: bool = False


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
        _get_console().print(message)


def error(message: str) -> None:
    """Print an error message."""
    if get_json_mode():
        json.dump({"error": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _get_console().print(f"[red]Error:[/red] {message}")


def table(
    title: str,
    columns: list[str | Col],
    rows: list[list[str]],
    data: Any = None,
    sections: list[int] | None = None,
) -> None:
    """Print a rich table or JSON data.

    Columns can be plain strings (backward compatible) or Col instances
    for per-column configuration (justify, style, max_width, no_wrap).

    ``sections`` is an optional list of row indices before which a visual
    section separator should be inserted (rich mode only).
    """
    if get_json_mode():
        if data is not None:
            json.dump(data, sys.stdout)
        else:
            col_names = [c.header if isinstance(c, Col) else c for c in columns]
            json.dump({"columns": col_names, "rows": rows}, sys.stdout)
        sys.stdout.write("\n")
    else:
        from rich.table import Table

        section_set = set(sections) if sections else set()
        t = Table(title=title)
        for col in columns:
            if isinstance(col, Col):
                kwargs: dict[str, Any] = {"justify": col.justify}
                if col.style:
                    kwargs["style"] = col.style
                if col.max_width is not None:
                    kwargs["max_width"] = col.max_width
                if col.no_wrap:
                    kwargs["no_wrap"] = True
                t.add_column(col.header, **kwargs)
            else:
                t.add_column(col)
        for i, row in enumerate(rows):
            if i in section_set:
                t.add_section()
            t.add_row(*row)
        _get_console().print(t)


def section(title: str) -> None:
    """Print a visual section separator. No-op in JSON mode."""
    if not get_json_mode():
        from rich.rule import Rule

        _get_console().print(Rule(title, style="dim", align="left"))


def kv(label: str, value: str, width: int = 14) -> None:
    """Print an aligned key-value pair. No-op in JSON mode."""
    if not get_json_mode():
        padded = f"{label}:".ljust(width)
        _get_console().print(f"[bold]{padded}[/bold] {value}")


def syntax(code: str, lexer: str = "yaml") -> None:
    """Print syntax-highlighted code. No-op in JSON mode."""
    if not get_json_mode():
        from rich.syntax import Syntax

        _get_console().print(Syntax(code, lexer, theme="monokai", padding=0))


def get_debug_mode() -> bool:
    """Check if --debug flag is set in the current click context."""
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj:
        return ctx.obj.get("debug", False)
    return False


def debug(message: str) -> None:
    """Print a debug message (only when --debug is active)."""
    if not get_debug_mode():
        return
    if get_json_mode():
        json.dump({"debug": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _get_console().print(f"[dim]{message}[/dim]")


def warn(message: str) -> None:
    """Print a warning message."""
    if get_json_mode():
        json.dump({"warning": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _get_console().print(f"[yellow]{message}[/yellow]")


def success(message: str) -> None:
    """Print a success message."""
    if get_json_mode():
        json.dump({"status": "ok", "message": message}, sys.stdout)
        sys.stdout.write("\n")
    else:
        _get_console().print(f"[green]{message}[/green]")


@contextmanager
def spinner(message: str):
    """Show a spinner while work is in progress. No-op in JSON mode."""
    if get_json_mode():
        yield None
    else:
        with _get_console().status(message, spinner="dots") as status:
            yield status


def update_spinner(status, message: str) -> None:
    """Update a spinner's message. Safe to call with None."""
    if status is not None:
        status.update(message)
