"""Tab bar widget — horizontal ticket tabs with status dots."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from duct_tui.theme import (
    ACCENT,
    DIM,
    DOT_ACTIVE,
    DOT_IDLE,
    GREEN,
    ICON_LOGO,
    TEXT,
    YELLOW,
)


class TabBar(Widget):
    """Horizontal bar with logo and ticket tabs."""

    DEFAULT_CSS = """
    TabBar {
        layout: horizontal;
        height: 1;
        width: 1fr;
    }
    TabBar .logo {
        width: auto;
        padding: 0 1 0 0;
    }
    TabBar .tab-item {
        width: auto;
        padding: 0 1;
    }
    """

    active_index: reactive[int] = reactive(0)

    class TabSelected(Message):
        """Fired when a tab is selected."""

        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(
        self,
        tickets: list[tuple[str, str]] | None = None,
        **kwargs,
    ) -> None:
        """tickets: list of (key, status_color) pairs."""
        super().__init__(**kwargs)
        self._tickets: list[tuple[str, str]] = tickets or []

    def compose(self) -> ComposeResult:
        yield Static(
            f"[{DIM}]{ICON_LOGO}[/] [{ACCENT} bold]duct[/]",
            classes="logo",
            markup=True,
        )
        for i, (key, _color) in enumerate(self._tickets):
            yield Static(
                self._render_tab(i, key, _color),
                classes="tab-item",
                markup=True,
                id=f"tab-{i}",
            )

    def set_tickets(self, tickets: list[tuple[str, str]]) -> None:
        """Update the ticket list and re-render."""
        self._tickets = tickets
        self._refresh_tabs()

    def watch_active_index(self, _old: int, _new: int) -> None:
        self._refresh_tabs()

    def _refresh_tabs(self) -> None:
        """Re-render all tab labels."""
        for i, (key, color) in enumerate(self._tickets):
            try:
                tab = self.query_one(f"#tab-{i}", Static)
                tab.update(self._render_tab(i, key, color))
            except Exception:
                pass

    def _render_tab(self, index: int, key: str, status_color: str) -> str:
        color_hex = _status_to_hex(status_color)
        dot = DOT_ACTIVE if status_color in ("green", "yellow") else DOT_IDLE
        is_active = index == self.active_index

        if is_active:
            return f"[{color_hex}]{dot}[/] [{ACCENT} bold]{key}[/]"
        return f"[{color_hex}]{dot}[/] [{DIM}]{key}[/]"

    def select_tab(self, index: int) -> None:
        if 0 <= index < len(self._tickets):
            self.active_index = index
            self.post_message(self.TabSelected(index))

    def next_tab(self) -> None:
        if self._tickets:
            self.select_tab((self.active_index + 1) % len(self._tickets))

    def prev_tab(self) -> None:
        if self._tickets:
            self.select_tab((self.active_index - 1) % len(self._tickets))


def _status_to_hex(color_name: str) -> str:
    return {
        "green": GREEN,
        "yellow": YELLOW,
        "red": "#ef4444",
        "dim": DIM,
        "lavender": "#aa96c8",
    }.get(color_name, DIM)
