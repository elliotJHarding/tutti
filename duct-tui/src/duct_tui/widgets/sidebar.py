"""Sidebar widget — scrollable navigation list with icons and status dots."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from duct_tui.data import AUTHORED_ARTIFACTS, SYNC_ARTIFACTS, TicketData
from duct_tui.theme import (
    ACCENT,
    ARTIFACT_ICONS,
    DIM,
    DOT_ACTIVE,
    DOT_IDLE,
    GREEN,
    ICON_SELECTED,
    TEXT,
    YELLOW,
)


class SidebarItem(Static):
    """A single selectable item in the sidebar."""

    DEFAULT_CSS = f"""
    SidebarItem {{
        height: auto;
        width: 1fr;
        padding: 0;
        color: {TEXT};
    }}
    SidebarItem:hover {{
        background: #2a2a2a;
    }}
    """

    def __init__(self, label: str, item_id: str, **kwargs) -> None:
        super().__init__(label, markup=True, **kwargs)
        self.item_id = item_id


class Sidebar(Widget):
    """Left navigation panel showing ticket info and artifact list."""

    DEFAULT_CSS = """
    Sidebar {
        width: 42;
        min-width: 42;
        max-width: 42;
    }
    """

    selected_index: reactive[int] = reactive(0)

    class ItemSelected(Message):
        """Fired when a sidebar item is selected."""

        def __init__(self, item_id: str) -> None:
            super().__init__()
            self.item_id = item_id

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[tuple[str, str]] = []  # (item_id, label_markup)
        self._ticket: TicketData | None = None

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="sidebar-scroll")

    def set_ticket(self, ticket: TicketData) -> None:
        """Update the sidebar to show a ticket's artifacts."""
        self._ticket = ticket
        self._items = []

        # Ticket info header
        dot = _status_dot(ticket.status_color)
        self._items.append((
            f"info:{ticket.key}",
            f"  {dot} [{TEXT} bold]{ticket.key}[/]\n  [{DIM}]{_truncate(ticket.summary, 36)}[/]",
        ))

        # Separator
        self._items.append(("sep:1", f"  [{DIM}]{'─' * 36}[/]"))

        # Authored artifacts
        for name in AUTHORED_ARTIFACTS:
            stem = name.replace(".md", "")
            icon = ARTIFACT_ICONS.get(stem, "·")
            present = name in ticket.artifacts
            if present:
                self._items.append((
                    f"artifact:{name}",
                    f"  {icon} [{TEXT}]{stem}[/]",
                ))
            else:
                self._items.append((
                    f"artifact:{name}",
                    f"  [{DIM}]{icon} {stem}[/]",
                ))

        # Separator
        self._items.append(("sep:2", f"  [{DIM}]{'─' * 36}[/]"))

        # Sync snapshots
        for name in SYNC_ARTIFACTS:
            stem = name.replace(".md", "")
            icon = ARTIFACT_ICONS.get(stem, "·")
            present = name in ticket.artifacts
            if present:
                self._items.append((
                    f"artifact:{name}",
                    f"  {icon} [{TEXT}]{stem}[/]",
                ))
            else:
                self._items.append((
                    f"artifact:{name}",
                    f"  [{DIM}]{icon} {stem}[/]",
                ))

        # Repos section (if any)
        if ticket.repos:
            self._items.append(("sep:3", f"  [{DIM}]{'─' * 36}[/]"))
            for repo in ticket.repos:
                self._items.append((
                    f"repo:{repo}",
                    f"  ⌂ [{TEXT}]{repo}[/]",
                ))

        self.selected_index = 0
        self._render_items()

    def _render_items(self) -> None:
        """Re-render all sidebar items."""
        scroll = self.query_one("#sidebar-scroll", VerticalScroll)
        scroll.remove_children()

        for i, (item_id, label) in enumerate(self._items):
            is_sep = item_id.startswith("sep:")
            if is_sep:
                scroll.mount(SidebarItem(label, item_id))
                continue

            # Selection indicator
            if i == self.selected_index:
                prefix = f"[{ACCENT}]{ICON_SELECTED}[/]"
                # Bold the label for selected item
                display_label = label.replace(f"[{TEXT}]", f"[{TEXT} bold]")
                scroll.mount(SidebarItem(f"{prefix}{display_label}", item_id))
            else:
                scroll.mount(SidebarItem(f" {label}", item_id))

    def watch_selected_index(self, _old: int, _new: int) -> None:
        if self._items:
            self._render_items()
            item_id, _ = self._items[self.selected_index]
            self.post_message(self.ItemSelected(item_id))

    def move_selection(self, delta: int) -> None:
        """Move selection by delta, skipping separators."""
        if not self._items:
            return
        new_idx = self.selected_index + delta
        # Skip separators
        while 0 <= new_idx < len(self._items):
            item_id, _ = self._items[new_idx]
            if not item_id.startswith("sep:"):
                break
            new_idx += delta
        if 0 <= new_idx < len(self._items):
            self.selected_index = new_idx

    @property
    def current_item_id(self) -> str | None:
        if self._items and 0 <= self.selected_index < len(self._items):
            return self._items[self.selected_index][0]
        return None


def _status_dot(color_name: str) -> str:
    """Return a colored status dot markup string."""
    hex_color = {
        "green": GREEN,
        "yellow": YELLOW,
        "red": "#ef4444",
        "dim": DIM,
    }.get(color_name, DIM)
    dot = DOT_ACTIVE if color_name in ("green", "yellow", "red") else DOT_IDLE
    return f"[{hex_color}]{dot}[/]"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
