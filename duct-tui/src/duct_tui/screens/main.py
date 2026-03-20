"""Main screen — composes all widgets and handles navigation."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.worker import Worker, get_current_worker

from duct_tui.data import WorkspaceData, load_workspace, read_artifact
from duct_tui.widgets.content import ContentPanel
from duct_tui.widgets.footer import FooterBar
from duct_tui.widgets.sidebar import Sidebar
from duct_tui.widgets.tab_bar import TabBar


class MainScreen(Screen):
    """Primary screen with tab bar, sidebar + content, and footer."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("tab", "next_ticket", "Next ticket", priority=True),
        Binding("shift+tab", "prev_ticket", "Prev ticket", priority=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("l", "open_content", "Open", show=False),
        Binding("enter", "open_content", "Open", show=False),
        Binding("h", "focus_sidebar", "Sidebar", show=False),
        Binding("escape", "focus_sidebar", "Back", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False, key_display="G"),
        Binding("ctrl+d", "page_down", "Page down", show=False),
        Binding("ctrl+u", "page_up", "Page up", show=False),
    ]

    def __init__(
        self,
        workspace_root: Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._workspace_root = workspace_root
        self._workspace: WorkspaceData | None = None
        self._active_ticket_idx = 0
        self._focus = "sidebar"  # "sidebar" or "content"

    def compose(self) -> ComposeResult:
        yield TabBar(id="tab-bar")
        with Horizontal(id="main-container"):
            yield Sidebar(id="sidebar")
            yield ContentPanel(id="content-panel")
        yield FooterBar(id="footer-bar")

    def on_mount(self) -> None:
        self._load_data()

    def _load_data(self) -> None:
        """Load workspace data (potentially slow, runs in worker)."""
        self.run_worker(self._do_load, thread=True)

    async def _do_load(self) -> WorkspaceData:
        return load_workspace(self._workspace_root)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == "success" and event.worker.result is not None:
            self._workspace = event.worker.result
            self._populate_ui()

    def _populate_ui(self) -> None:
        """Populate all widgets from loaded workspace data."""
        ws = self._workspace
        if not ws or not ws.tickets:
            self.query_one("#content-panel", ContentPanel).show_placeholder(
                "No tickets found in workspace"
            )
            return

        # Update tab bar
        tab_data = [(t.key, t.status_color) for t in ws.tickets]
        tab_bar = self.query_one("#tab-bar", TabBar)
        tab_bar.set_tickets(tab_data)
        tab_bar.active_index = self._active_ticket_idx

        # Show first ticket in sidebar
        self._show_ticket(self._active_ticket_idx)

    def _show_ticket(self, index: int) -> None:
        """Show a ticket's data in the sidebar and content."""
        ws = self._workspace
        if not ws or index >= len(ws.tickets):
            return

        self._active_ticket_idx = index
        ticket = ws.tickets[index]

        # Update sidebar
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.set_ticket(ticket)

        # Show TICKET.md by default, or placeholder
        if ticket.ticket_md:
            self.query_one("#content-panel", ContentPanel).show_markdown(
                ticket.ticket_md
            )
        else:
            self.query_one("#content-panel", ContentPanel).show_placeholder(
                f"No TICKET.md found for {ticket.key}"
            )

    # --- Tab bar events ---

    def on_tab_bar_tab_selected(self, event: TabBar.TabSelected) -> None:
        self._show_ticket(event.index)

    # --- Sidebar events ---

    def on_sidebar_item_selected(self, event: Sidebar.ItemSelected) -> None:
        item_id = event.item_id
        if item_id.startswith("artifact:"):
            filename = item_id.split(":", 1)[1]
            self._show_artifact(filename)
        elif item_id.startswith("info:"):
            # Show TICKET.md
            ws = self._workspace
            if ws and self._active_ticket_idx < len(ws.tickets):
                ticket = ws.tickets[self._active_ticket_idx]
                if ticket.ticket_md:
                    self.query_one("#content-panel", ContentPanel).show_markdown(
                        ticket.ticket_md
                    )

    def _show_artifact(self, filename: str) -> None:
        """Load and display an artifact in the content panel."""
        ws = self._workspace
        if not ws or self._active_ticket_idx >= len(ws.tickets):
            return

        ticket = ws.tickets[self._active_ticket_idx]
        content = read_artifact(ticket, filename)

        panel = self.query_one("#content-panel", ContentPanel)
        if content:
            panel.show_markdown(content)
        else:
            stem = filename.replace(".md", "")
            panel.show_placeholder(f"{stem} — not yet created")

    # --- Navigation actions ---

    def action_quit(self) -> None:
        self.app.exit()

    def action_next_ticket(self) -> None:
        tab_bar = self.query_one("#tab-bar", TabBar)
        tab_bar.next_tab()

    def action_prev_ticket(self) -> None:
        tab_bar = self.query_one("#tab-bar", TabBar)
        tab_bar.prev_tab()

    def action_cursor_down(self) -> None:
        if self._focus == "sidebar":
            self.query_one("#sidebar", Sidebar).move_selection(1)
        else:
            self.query_one("#content-panel", ContentPanel).scroll_down()

    def action_cursor_up(self) -> None:
        if self._focus == "sidebar":
            self.query_one("#sidebar", Sidebar).move_selection(-1)
        else:
            self.query_one("#content-panel", ContentPanel).scroll_up()

    def action_open_content(self) -> None:
        self._focus = "content"
        self.query_one("#footer-bar", FooterBar).set_context("content")

    def action_focus_sidebar(self) -> None:
        self._focus = "sidebar"
        self.query_one("#footer-bar", FooterBar).set_context("sidebar")

    def action_scroll_top(self) -> None:
        if self._focus == "content":
            self.query_one("#content-panel", ContentPanel).scroll_to_top()

    def action_scroll_bottom(self) -> None:
        if self._focus == "content":
            self.query_one("#content-panel", ContentPanel).scroll_to_bottom()

    def action_page_down(self) -> None:
        if self._focus == "content":
            self.query_one("#content-panel", ContentPanel).page_down()

    def action_page_up(self) -> None:
        if self._focus == "content":
            self.query_one("#content-panel", ContentPanel).page_up()

    # --- Background sync polling ---

    def start_sync_polling(self, interval: float = 30.0) -> None:
        """Start periodic workspace data refresh."""
        self.set_interval(interval, self._poll_sync)

    def _poll_sync(self) -> None:
        """Re-load workspace data in background."""
        self.run_worker(self._do_load, thread=True)
