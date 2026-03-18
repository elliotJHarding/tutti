"""Content panel widget — markdown viewer for artifacts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Markdown, Static

from tutti_tui.theme import DIM, TEXT


class ContentPanel(Widget):
    """Right pane showing the selected artifact's content."""

    DEFAULT_CSS = f"""
    ContentPanel {{
        width: 1fr;
        height: 1fr;
    }}
    ContentPanel #content-scroll {{
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }}
    ContentPanel #content-md {{
        width: 1fr;
        max-width: 120;
        padding: 0 2;
        color: {TEXT};
    }}
    ContentPanel #content-placeholder {{
        width: 1fr;
        padding: 1 2;
        color: {DIM};
        text-align: center;
    }}
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_content: str | None = None

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="content-scroll"):
            yield Markdown("", id="content-md")
            yield Static(
                "Select an artifact to view its content",
                id="content-placeholder",
            )

    def on_mount(self) -> None:
        self.query_one("#content-md", Markdown).display = False

    def show_markdown(self, content: str) -> None:
        """Display markdown content in the panel."""
        self._current_content = content

        md_widget = self.query_one("#content-md", Markdown)
        placeholder = self.query_one("#content-placeholder", Static)

        # Strip frontmatter before display
        display_content = _strip_frontmatter(content)

        md_widget.update(display_content)
        md_widget.display = True
        placeholder.display = False

        # Scroll to top
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_home(animate=False)

    def show_placeholder(self, message: str) -> None:
        """Show a placeholder message when no content is available."""
        self._current_content = None

        md_widget = self.query_one("#content-md", Markdown)
        placeholder = self.query_one("#content-placeholder", Static)

        md_widget.display = False
        placeholder.update(message)
        placeholder.display = True

    def scroll_down(self, lines: int = 3) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_relative(y=lines)

    def scroll_up(self, lines: int = 3) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_relative(y=-lines)

    def scroll_to_top(self) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_home(animate=False)

    def scroll_to_bottom(self) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_end(animate=False)

    def page_down(self) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_page_down()

    def page_up(self) -> None:
        scroll = self.query_one("#content-scroll", ScrollableContainer)
        scroll.scroll_page_up()


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content for display."""
    if not content.startswith("---"):
        return content
    lines = content.split("\n")
    # Find closing ---
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return content
