"""Workspace directory layout helpers for tutti.

The workspace is a tree of ticket directories, optionally grouped under epic
directories.  Both kinds of directory are named ``{KEY}-{slug}``, where KEY is
a Jira-style ticket key (e.g. ERSC-1278).

A "ticket directory" is a leaf that contains an ``orchestrator/`` subdirectory.
An "epic directory" is one that itself matches the key pattern *and* contains
nested ticket directories.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from tutti.markdown import TICKET_KEY_PATTERN

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    """Convert *text* to a lowercase URL-style slug (a-z, 0-9, hyphens)."""
    s = _SLUG_STRIP_RE.sub("-", text.lower())
    return s.strip("-")


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
# Directory resolution
# ---------------------------------------------------------------------------

def _key_from_dirname(name: str) -> str | None:
    """Extract a ticket key from the start of *name*, or return None."""
    m = re.match(rf"^({TICKET_KEY_PATTERN.pattern})-", name)
    return m.group(1) if m else None


def _is_ticket_dir(path: Path) -> bool:
    """True when *path* looks like a leaf ticket directory."""
    return path.is_dir() and (path / "orchestrator").is_dir()


def _contains_ticket_dirs(path: Path) -> bool:
    """True when *path* contains at least one child that is a ticket dir."""
    if not path.is_dir():
        return False
    for child in path.iterdir():
        if child.is_dir() and _key_from_dirname(child.name) and _is_ticket_dir(child):
            return True
    return False


def resolve_ticket_dir(root: Path, key: str) -> Path | None:
    """Find an existing ticket directory for *key* under *root*.

    Searches both the root level and one level of epic subdirectories.
    Returns the path if found, otherwise None.
    """
    prefix = f"{key}-"
    # Check root-level dirs.
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.startswith(prefix):
            if _is_ticket_dir(child):
                return child
    # Check inside epic dirs (one level deep).
    for epic in sorted(root.iterdir()):
        if not epic.is_dir() or not _key_from_dirname(epic.name):
            continue
        for child in sorted(epic.iterdir()):
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
    epic_key: str | None = None,
    epic_summary: str | None = None,
) -> Path:
    """Create (or relocate) a ticket directory under *root* and return its path.

    When *epic_key* is provided the ticket is placed inside the corresponding
    epic directory (created if necessary).  If the ticket already exists
    elsewhere it is moved to the correct location.
    """
    existing = resolve_ticket_dir(root, key)
    dirname = ticket_dir_name(key, summary)

    if epic_key:
        epic_name = ticket_dir_name(epic_key, epic_summary or epic_key)
        parent = root / epic_name
        parent.mkdir(parents=True, exist_ok=True)
    else:
        parent = root

    target = parent / dirname

    if existing and existing != target:
        # Move to new location (e.g. root -> epic subdir).
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(existing), str(target))
    elif not existing:
        target.mkdir(parents=True, exist_ok=True)

    # Always ensure the orchestrator subdirectory exists.
    (target / "orchestrator").mkdir(exist_ok=True)
    return target


def orchestrator_dir(ticket_dir: Path) -> Path:
    """Return the ``orchestrator/`` subdirectory inside *ticket_dir*, creating it if needed."""
    d = ticket_dir / "orchestrator"
    d.mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

def enumerate_ticket_dirs(root: Path) -> list[tuple[str, Path]]:
    """Scan *root* for all leaf ticket directories.

    Returns a list of ``(ticket_key, path)`` pairs.  Ticket dirs nested under
    epic dirs are included; the epic dirs themselves are not.
    """
    results: list[tuple[str, Path]] = []
    if not root.is_dir():
        return results

    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        key = _key_from_dirname(child.name)
        if not key:
            continue

        if _is_ticket_dir(child) and not _contains_ticket_dirs(child):
            # Leaf ticket dir at root level.
            results.append((key, child))
        else:
            # Potential epic dir — look inside for ticket dirs.
            for sub in sorted(child.iterdir()):
                if not sub.is_dir():
                    continue
                sub_key = _key_from_dirname(sub.name)
                if sub_key and _is_ticket_dir(sub):
                    results.append((sub_key, sub))

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


def restore_ticket(
    root: Path,
    key: str,
    epic_key: str | None = None,
) -> Path | None:
    """Move a ticket directory from ``.archive`` back into the workspace.

    If *epic_key* is given the ticket is placed under the corresponding epic
    directory.  Returns the restored path, or None if nothing was found in the
    archive.
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

    if epic_key:
        # Find an existing epic dir, or fall back to root.
        epic_prefix = f"{epic_key}-"
        parent = root
        for child in sorted(root.iterdir()):
            if child.is_dir() and child.name.startswith(epic_prefix):
                parent = child
                break
    else:
        parent = root

    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / src.name
    shutil.move(str(src), str(dest))
    return dest
