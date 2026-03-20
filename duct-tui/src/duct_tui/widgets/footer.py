"""Footer bar widget — context-sensitive keybinding hints."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static
from textual.app import ComposeResult

from duct_tui.theme import ACCENT, DIM


# Keybinding sets for different focus contexts
SIDEBAR_BINDINGS = [
    ("j/k", "navigate"),
    ("l/Enter", "open"),
    ("Tab", "next ticket"),
    ("S-Tab", "prev ticket"),
    ("q", "quit"),
]

CONTENT_BINDINGS = [
    ("j/k", "scroll"),
    ("h/Esc", "sidebar"),
    ("g/G", "top/bottom"),
    ("Ctrl+d/u", "page"),
    ("Tab", "next ticket"),
    ("q", "quit"),
]


class FooterBar(Widget):
    """Bottom bar showing context-sensitive keybinding hints."""

    DEFAULT_CSS = f"""
    FooterBar {{
        layout: horizontal;
        height: 1;
        width: 1fr;
        background: #1a1a1a;
        padding: 0 1;
    }}
    FooterBar #footer-keys {{
        width: 1fr;
    }}
    FooterBar #footer-sync {{
        width: auto;
        min-width: 12;
        text-align: right;
    }}
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._focus_context = "sidebar"

    def compose(self) -> ComposeResult:
        yield Static(
            self._render_bindings(SIDEBAR_BINDINGS),
            id="footer-keys",
            markup=True,
        )
        yield Static(
            f"[{DIM}]sync: ok[/]",
            id="footer-sync",
            markup=True,
        )

    def set_context(self, context: str) -> None:
        """Update displayed bindings for the given focus context."""
        self._focus_context = context
        bindings = SIDEBAR_BINDINGS if context == "sidebar" else CONTENT_BINDINGS
        self.query_one("#footer-keys", Static).update(
            self._render_bindings(bindings)
        )

    def set_sync_status(self, status: str, error: bool = False) -> None:
        """Update the sync status indicator."""
        color = "#ef4444" if error else DIM
        self.query_one("#footer-sync", Static).update(
            f"[{color}]sync: {status}[/]"
        )

    def _render_bindings(self, bindings: list[tuple[str, str]]) -> str:
        parts = []
        for key, desc in bindings:
            parts.append(f"[{ACCENT} bold]{key}[/] [{DIM}]{desc}[/]")
        return "  ".join(parts)
