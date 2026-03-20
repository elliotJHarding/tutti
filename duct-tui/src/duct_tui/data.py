"""Workspace data loading — wraps the duct library for TUI consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from duct.api import (
    enumerate_ticket_dirs,
    find_workspace_root,
    load_config,
    orchestrator_dir,
)
from duct.markdown import extract_table, parse_frontmatter


# Orchestrator-authored artifacts (display order)
AUTHORED_ARTIFACTS = [
    "BACKGROUND.md",
    "AC.md",
    "SPEC.md",
    "IMPLEMENTATION.md",
    "VERIFICATION.md",
    "DEPLOYMENT.md",
    "QA.md",
    "ORCHESTRATOR.md",
]

# Sync snapshot files (display order)
SYNC_ARTIFACTS = [
    "TICKET.md",
    "PULL_REQUESTS.md",
    "CI.md",
    "CLAUDE_SESSIONS.md",
    "WORKSPACE.md",
]


@dataclass
class TicketData:
    """All displayable data for a single ticket."""

    key: str
    summary: str
    status: str
    category: str
    path: Path
    artifacts: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    ticket_md: str | None = None

    @property
    def status_color(self) -> str:
        """Map ticket status to a theme color name."""
        s = self.status.lower()
        if "progress" in s or "active" in s:
            return "green"
        if "done" in s or "closed" in s or "resolved" in s:
            return "dim"
        if "testing" in s and "fail" in s:
            return "red"
        if "testing" in s or "review" in s or "waiting" in s:
            return "yellow"
        return "yellow"  # default for to-do, pending, etc.


@dataclass
class WorkspaceData:
    """Snapshot of all tickets in the workspace."""

    root: Path
    tickets: list[TicketData] = field(default_factory=list)


def load_ticket(key: str, ticket_dir: Path) -> TicketData:
    """Load a single ticket's data from disk."""
    orch = orchestrator_dir(ticket_dir)

    # Discover artifacts
    artifacts: list[str] = []
    for name in AUTHORED_ARTIFACTS + SYNC_ARTIFACTS:
        if (orch / name).is_file():
            artifacts.append(name)

    # Discover repo worktrees (non-orchestrator subdirectories)
    repos: list[str] = []
    for child in sorted(ticket_dir.iterdir()):
        if child.is_dir() and child.name not in ("orchestrator", ".git", "__pycache__"):
            repos.append(child.name)

    # Parse TICKET.md for metadata
    summary = ""
    status = ""
    category = ""
    metadata: dict[str, str] = {}
    ticket_md: str | None = None

    ticket_path = orch / "TICKET.md"
    if ticket_path.is_file():
        ticket_md = ticket_path.read_text(encoding="utf-8")
        _fm, body = parse_frontmatter(ticket_md)

        # Extract summary from H1 heading: "# KEY: Summary"
        for line in body.splitlines():
            if line.startswith("# "):
                parts = line[2:].split(":", 1)
                if len(parts) == 2:
                    summary = parts[1].strip()
                break

        # Extract metadata table
        rows = extract_table(body)
        for row in rows:
            field_name = row.get("Field", "").strip()
            value = row.get("Value", "").strip()
            if field_name and value:
                metadata[field_name] = value

        status = metadata.get("Status", "")
        category = metadata.get("Category", "")

    return TicketData(
        key=key,
        summary=summary or key,
        status=status,
        category=category,
        path=ticket_dir,
        artifacts=artifacts,
        repos=repos,
        metadata=metadata,
        ticket_md=ticket_md,
    )


def load_workspace(root: Path | None = None) -> WorkspaceData:
    """Scan workspace and return all ticket data for display."""
    if root is None:
        root = find_workspace_root()

    # Validate config exists
    load_config(root)

    ticket_dirs = enumerate_ticket_dirs(root)
    tickets = [load_ticket(key, path) for key, path in ticket_dirs]

    # Sort by key for stable ordering
    tickets.sort(key=lambda t: t.key)

    return WorkspaceData(root=root, tickets=tickets)


def read_artifact(ticket: TicketData, filename: str) -> str | None:
    """Read an artifact file's content, returning None if it doesn't exist."""
    path = orchestrator_dir(ticket.path) / filename
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None
