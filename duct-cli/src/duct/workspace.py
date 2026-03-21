"""Workspace directory layout helpers for duct.

Ticket directories live directly under the workspace root, named
``{KEY}-{slug}`` where KEY is a Jira-style ticket key (e.g. ERSC-1278).

A "ticket directory" contains an ``orchestrator/`` subdirectory.
Epic metadata lives in ``{root}/epics/`` as markdown files, and each ticket's
``orchestrator/`` directory optionally symlinks ``EPIC.md`` to its parent epic file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from duct.markdown import TICKET_KEY_PATTERN, generate_frontmatter
from duct.models import RepoEntry, Workspace

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    """Convert *text* to a lowercase URL-style slug (a-z, 0-9, hyphens)."""
    s = _SLUG_STRIP_RE.sub("-", text.lower())
    return s.strip("-")


def branch_name(key: str, summary: str, issue_type: str) -> str:
    """Build a branch name like ``feature/ERSC-1278-case-file-updates``.

    Uses ``bugfix/`` for PS- project tickets or Bug issue types, ``feature/``
    for everything else.  Truncated to 80 characters.
    """
    prefix = "bugfix" if key.startswith("PS-") or issue_type.lower() == "bug" else "feature"
    return f"{prefix}/{key.upper()}-{slug(summary)}"[:80]


def read_issue_type(ticket_dir: Path) -> str:
    """Read the issue type from ``orchestrator/TICKET.md``.

    Returns the type string (e.g. ``"Story"``, ``"Bug"``), or an empty string
    if the file is missing or the field is not found.
    """
    ticket_md = ticket_dir / "orchestrator" / "TICKET.md"
    if not ticket_md.exists():
        return ""
    for line in ticket_md.read_text().splitlines():
        if line.strip().startswith("| Type |"):
            parts = line.split("|")
            if len(parts) >= 3:
                return parts[2].strip()
    return ""


def ticket_dir_name(key: str, summary: str) -> str:
    """Return the canonical directory name for a ticket.

    Format: ``{KEY}-{slugified-summary}``, truncated so the total length
    stays under 80 characters.
    """
    prefix = f"{key}-"
    max_slug = 80 - len(prefix)
    s = slug(summary)
    if len(s) > max_slug:
        s = s[:max_slug].rstrip("-")
    return f"{prefix}{s}"


# ---------------------------------------------------------------------------
# workspace.json read/write
# ---------------------------------------------------------------------------


def load_workspace(workspace_dir: Path) -> Workspace:
    """Load workspace metadata from .duct/workspace.json."""
    json_path = workspace_dir / ".duct" / "workspace.json"
    if not json_path.exists():
        raise FileNotFoundError(f"No workspace.json at {json_path}")
    data = json.loads(json_path.read_text())
    repos = [
        RepoEntry(
            name=r["name"],
            origin=r.get("origin", ""),
            branch=r.get("branch", ""),
            base_branch=r.get("base_branch", "main"),
        )
        for r in data.get("repos", [])
    ]
    return Workspace(
        ticket_key=data["ticket_key"],
        created_at=data.get("created_at", ""),
        branch_type=data.get("branch_type", "feature"),
        default_branch=data.get("default_branch", ""),
        priority=data.get("priority", 0),
        repos=repos,
        path=str(workspace_dir),
    )


def save_workspace(ws: Workspace) -> None:
    """Write workspace metadata to .duct/workspace.json."""
    if not ws.path:
        raise ValueError("Workspace.path must be set before saving")
    duct_dir = Path(ws.path) / ".duct"
    duct_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "ticket_key": ws.ticket_key,
        "created_at": ws.created_at,
        "branch_type": ws.branch_type,
        "default_branch": ws.default_branch,
        "priority": ws.priority,
        "repos": [
            {
                "name": r.name,
                "origin": r.origin,
                "branch": r.branch,
                "base_branch": r.base_branch,
            }
            for r in ws.repos
        ],
    }
    (duct_dir / "workspace.json").write_text(json.dumps(data, indent=2))


def _init_workspace_json(workspace_dir: Path, ticket_key: str) -> None:
    """Write a minimal workspace.json if one does not already exist."""
    json_path = workspace_dir / ".duct" / "workspace.json"
    if json_path.exists():
        return
    ws = Workspace(
        ticket_key=ticket_key,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        path=str(workspace_dir),
    )
    save_workspace(ws)


# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

def _key_from_dirname(name: str) -> str | None:
    """Extract a ticket key from the start of *name*, or return None."""
    m = re.match(rf"^({TICKET_KEY_PATTERN.pattern})-", name)
    return m.group(1) if m else None


def _is_ticket_dir(path: Path) -> bool:
    """True when *path* looks like a leaf ticket directory."""
    return path.is_dir() and (path / "orchestrator").is_dir()


def resolve_ticket_dir(root: Path, key: str) -> Path | None:
    """Find an existing ticket directory for *key* under *root*.

    Only scans the root level (flat layout).
    Returns the path if found, otherwise None.
    """
    prefix = f"{key}-"
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.startswith(prefix) and _is_ticket_dir(child):
            return child
    return None


# ---------------------------------------------------------------------------
# Directory creation / mutation
# ---------------------------------------------------------------------------

def ensure_ticket_dir(
    root: Path,
    key: str,
    summary: str,
) -> Path:
    """Create a ticket directory directly under *root* and return its path.

    All tickets are placed at the root level (flat layout).  If the ticket
    already exists with a different name (summary changed), it is renamed.
    """
    existing = resolve_ticket_dir(root, key)
    dirname = ticket_dir_name(key, summary)
    target = root / dirname

    if existing and existing != target:
        shutil.move(str(existing), str(target))
    elif not existing:
        target.mkdir(parents=True, exist_ok=True)

    # Always ensure the orchestrator subdirectory exists.
    (target / "orchestrator").mkdir(exist_ok=True)
    _init_workspace_json(target, key)
    return target


def ensure_epic_link(
    root: Path,
    ticket_dir: Path,
    epic_key: str,
    epic_summary: str | None = None,
) -> Path:
    """Create the epic metadata file and symlink EPIC.md in the orchestrator dir.

    - Creates ``{root}/epics/{EPIC_KEY}-{slug}.md`` if it doesn't exist.
    - Creates or updates ``{ticket_dir}/orchestrator/EPIC.md`` as a relative
      symlink to the epic file.

    Returns the path to the epic metadata file.
    """
    epics_dir = root / "epics"
    epics_dir.mkdir(exist_ok=True)

    epic_filename = ticket_dir_name(epic_key, epic_summary or epic_key) + ".md"
    epic_file = epics_dir / epic_filename

    if not epic_file.exists():
        content = generate_frontmatter(source="sync")
        content += f"\n# {epic_key}: {epic_summary or epic_key}\n"
        epic_file.write_text(content)

    orch_dir = ticket_dir / "orchestrator"
    orch_dir.mkdir(exist_ok=True)
    link_path = orch_dir / "EPIC.md"
    rel_target = os.path.relpath(epic_file, orch_dir)

    if link_path.is_symlink():
        current_target = os.readlink(link_path)
        if current_target != rel_target:
            link_path.unlink()
            link_path.symlink_to(rel_target)
    elif link_path.exists():
        # A regular file — replace with symlink.
        link_path.unlink()
        link_path.symlink_to(rel_target)
    else:
        link_path.symlink_to(rel_target)

    return epic_file


def orchestrator_dir(ticket_dir: Path) -> Path:
    """Return the ``orchestrator/`` subdirectory inside *ticket_dir*, creating it if needed."""
    d = ticket_dir / "orchestrator"
    d.mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

def enumerate_ticket_dirs(root: Path) -> list[tuple[str, Path]]:
    """Scan *root* for all ticket directories (flat layout).

    Returns a list of ``(ticket_key, path)`` pairs.  Only scans the root
    level — tickets are never nested.
    """
    results: list[tuple[str, Path]] = []
    if not root.is_dir():
        return results

    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        key = _key_from_dirname(child.name)
        if key and _is_ticket_dir(child):
            results.append((key, child))

    return results


# ---------------------------------------------------------------------------
# Archive / restore
# ---------------------------------------------------------------------------

def archive_ticket(root: Path, key: str) -> Path | None:
    """Move the ticket directory for *key* into ``root/.archive/``.

    Returns the archive path, or None if no matching ticket dir was found.
    """
    src = resolve_ticket_dir(root, key)
    if src is None:
        return None
    archive = root / ".archive"
    archive.mkdir(exist_ok=True)
    dest = archive / src.name
    shutil.move(str(src), str(dest))
    return dest


def restore_ticket(root: Path, key: str) -> Path | None:
    """Move a ticket directory from ``.archive`` back into the workspace.

    Restores to the workspace root (flat layout).  Returns the restored path,
    or None if nothing was found in the archive.
    """
    archive = root / ".archive"
    if not archive.is_dir():
        return None

    prefix = f"{key}-"
    src: Path | None = None
    for child in sorted(archive.iterdir()):
        if child.is_dir() and child.name.startswith(prefix):
            src = child
            break
    if src is None:
        return None

    dest = root / src.name
    shutil.move(str(src), str(dest))
    return dest
