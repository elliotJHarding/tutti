"""DuctApp — main entry point for the duct TUI."""

from __future__ import annotations

import sys
from pathlib import Path

from textual.app import App

from duct_tui.screens.main import MainScreen
from duct_tui.theme import APP_CSS


class DuctApp(App):
    """Terminal UI for duct workspace management."""

    CSS = APP_CSS
    TITLE = "duct"

    def __init__(self, workspace_root: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._workspace_root = workspace_root

    def on_mount(self) -> None:
        self.push_screen(MainScreen(workspace_root=self._workspace_root))


def main() -> None:
    """CLI entry point."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    app = DuctApp(workspace_root=root)
    app.run()


if __name__ == "__main__":
    main()
