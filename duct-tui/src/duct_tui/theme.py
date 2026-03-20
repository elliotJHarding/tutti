"""Houston-inspired color palette and Textual CSS for the duct TUI."""

# Houston RGB palette
ACCENT = "#d98e64"       # rgb(217, 142, 100) — highlights, active elements
GREEN = "#10b981"        # rgb(16, 185, 129)  — active/done status
YELLOW = "#f59e0b"       # rgb(245, 158, 11)  — waiting/incomplete
RED = "#ef4444"          # rgb(239, 68, 68)   — error/critical
DIM = "#646464"          # rgb(100, 100, 100) — borders, muted text
TEXT = "#d4d4d4"         # rgb(212, 212, 212) — normal body text
LAVENDER = "#aa96c8"     # rgb(170, 150, 200) — analysis, code blocks
BACKGROUND = "#1e1e1e"   # dark background
SURFACE = "#252525"      # slightly lighter surface

# Status dot characters
DOT_ACTIVE = "●"     # green — active
DOT_WAITING = "◉"    # yellow — waiting
DOT_IDLE = "○"       # dim — idle
DOT_ERROR = "✕"      # red — terminated/error

# UI icons
ICON_LOGO = "※"
ICON_TICKET = "≡"
ICON_WORKSPACE = "⌂"
ICON_PR = "⑂"
ICON_SESSION = "◇"
ICON_SELECTED = "▎"

# Artifact icons — maps filename stem to display icon
ARTIFACT_ICONS: dict[str, str] = {
    "TICKET": "≡",
    "BACKGROUND": "◈",
    "AC": "✓",
    "SPEC": "◆",
    "IMPLEMENTATION": "⚙",
    "VERIFICATION": "✔",
    "DEPLOYMENT": "▲",
    "QA": "⊘",
    "ORCHESTRATOR": "※",
    "PULL_REQUESTS": "⑂",
    "CI": "⏣",
    "CLAUDE_SESSIONS": "◇",
    "WORKSPACE": "⌂",
}

APP_CSS = f"""
Screen {{
    background: {BACKGROUND};
}}

#tab-bar {{
    dock: top;
    height: 1;
    background: {BACKGROUND};
    color: {TEXT};
}}

#main-container {{
    height: 1fr;
}}

#sidebar {{
    width: 42;
    min-width: 42;
    max-width: 42;
    background: {BACKGROUND};
    border-right: solid {DIM};
    overflow-y: auto;
    padding: 0 1;
}}

#sidebar:focus-within {{
    border-right: solid {ACCENT};
}}

#content-scroll {{
    background: {BACKGROUND};
    overflow-y: auto;
}}

#content-wrapper {{
    max-width: 120;
    width: 1fr;
    align-horizontal: center;
    padding: 0 2;
}}

#content-panel {{
    color: {TEXT};
    width: 1fr;
    max-width: 120;
}}

#footer-bar {{
    dock: bottom;
    height: 1;
    background: {BACKGROUND};
    color: {DIM};
}}

.sidebar-item {{
    height: auto;
    padding: 0;
    color: {TEXT};
}}

.sidebar-item.--highlight {{
    color: {TEXT};
}}

.sidebar-separator {{
    height: 1;
    color: {DIM};
}}

.tab-label {{
    padding: 0 1;
}}

.tab-active {{
    text-style: bold;
    color: {ACCENT};
}}

.tab-inactive {{
    color: {DIM};
}}

.dim-text {{
    color: {DIM};
}}

.accent-text {{
    color: {ACCENT};
}}

Markdown {{
    margin: 0;
    padding: 0;
    background: {BACKGROUND};
}}

MarkdownH1 {{
    color: {ACCENT};
    text-style: bold;
    margin: 0 0 1 0;
    padding: 0;
    background: {BACKGROUND};
    border-bottom: solid {DIM};
}}

MarkdownH2 {{
    color: {TEXT};
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0;
    background: {BACKGROUND};
}}

MarkdownH3 {{
    color: {TEXT};
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0;
    background: {BACKGROUND};
}}

MarkdownFence {{
    background: {SURFACE};
    color: {LAVENDER};
    margin: 0;
    padding: 0 1;
}}

MarkdownBlockQuote {{
    border-left: outer {ACCENT};
    margin: 0;
    padding: 0 0 0 1;
    background: {BACKGROUND};
}}

MarkdownTable {{
    margin: 0;
    padding: 0;
    background: {BACKGROUND};
}}
"""
