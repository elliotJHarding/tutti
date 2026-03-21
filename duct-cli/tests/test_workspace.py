"""Tests for duct.workspace utilities."""

import json
import os
from pathlib import Path

import pytest

from duct.models import RepoEntry, Workspace
from duct.workspace import (
    archive_ticket,
    branch_name,
    ensure_epic_link,
    ensure_ticket_dir,
    enumerate_ticket_dirs,
    load_workspace,
    orchestrator_dir,
    read_issue_type,
    resolve_ticket_dir,
    restore_ticket,
    save_workspace,
    slug,
    ticket_dir_name,
)

# ---------------------------------------------------------------------------
# slug()
# ---------------------------------------------------------------------------

class TestSlug:
    def test_basic(self):
        assert slug("Fix Auth Middleware") == "fix-auth-middleware"

    def test_special_characters(self):
        assert slug("Hello, World! (v2)") == "hello-world-v2"

    def test_already_clean(self):
        assert slug("already-clean") == "already-clean"

    def test_leading_trailing_stripped(self):
        assert slug("  --hello--  ") == "hello"

    def test_collapses_multiple_hyphens(self):
        assert slug("a   b") == "a-b"


# ---------------------------------------------------------------------------
# branch_name()
# ---------------------------------------------------------------------------

class TestBranchName:
    def test_feature_branch(self):
        assert branch_name("ERSC-1278", "case file updates", "Story") == "feature/ERSC-1278-case-file-updates"

    def test_ps_project_is_bugfix(self):
        assert branch_name("PS-412", "null pointer on submit", "Task") == "bugfix/PS-412-null-pointer-on-submit"

    def test_bug_type_is_bugfix(self):
        assert branch_name("AZIE-100", "login crash", "Bug") == "bugfix/AZIE-100-login-crash"

    def test_key_uppercased(self):
        result = branch_name("ersc-50", "some title", "Story")
        assert result.startswith("feature/ERSC-50-")

    def test_truncation(self):
        long_title = "a very long title that goes on and on " * 5
        result = branch_name("ERSC-1278", long_title, "Story")
        assert len(result) <= 80


# ---------------------------------------------------------------------------
# read_issue_type()
# ---------------------------------------------------------------------------

class TestReadIssueType:
    def test_reads_type(self, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-100-test"
        (ticket_dir / "orchestrator").mkdir(parents=True)
        (ticket_dir / "orchestrator" / "TICKET.md").write_text(
            "| Field | Value |\n|-------|-------|\n| Status | Open |\n| Type | Bug |\n"
        )
        assert read_issue_type(ticket_dir) == "Bug"

    def test_missing_file(self, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-200-test"
        (ticket_dir / "orchestrator").mkdir(parents=True)
        assert read_issue_type(ticket_dir) == ""

    def test_no_type_row(self, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-300-test"
        (ticket_dir / "orchestrator").mkdir(parents=True)
        (ticket_dir / "orchestrator" / "TICKET.md").write_text("# Ticket\nNo table here.\n")
        assert read_issue_type(ticket_dir) == ""


# ---------------------------------------------------------------------------
# ticket_dir_name()
# ---------------------------------------------------------------------------

class TestTicketDirName:
    def test_format(self):
        result = ticket_dir_name("ERSC-1278", "Fix auth middleware")
        assert result == "ERSC-1278-fix-auth-middleware"

    def test_truncation(self):
        long_summary = "a" * 200
        name = ticket_dir_name("ERSC-1", long_summary)
        assert len(name) <= 80
        assert name.startswith("ERSC-1-")


# ---------------------------------------------------------------------------
# resolve_ticket_dir()
# ---------------------------------------------------------------------------

class TestResolveTicketDir:
    def test_finds_at_root(self, tmp_workspace: Path):
        d = tmp_workspace / "ERSC-100-some-task"
        d.mkdir()
        (d / "orchestrator").mkdir()
        assert resolve_ticket_dir(tmp_workspace, "ERSC-100") == d

    def test_returns_none_when_missing(self, tmp_workspace: Path):
        assert resolve_ticket_dir(tmp_workspace, "ERSC-999") is None


# ---------------------------------------------------------------------------
# ensure_ticket_dir()
# ---------------------------------------------------------------------------

class TestEnsureTicketDir:
    def test_creates_new_dir(self, tmp_workspace: Path):
        path = ensure_ticket_dir(tmp_workspace, "ERSC-200", "New feature")
        assert path.exists()
        assert (path / "orchestrator").is_dir()
        assert path.name == "ERSC-200-new-feature"
        assert path.parent == tmp_workspace

    def test_renames_when_summary_changes(self, tmp_workspace: Path):
        original = ensure_ticket_dir(tmp_workspace, "ERSC-300", "Old name")
        assert original.parent == tmp_workspace

        renamed = ensure_ticket_dir(tmp_workspace, "ERSC-300", "New name")
        assert not original.exists()
        assert renamed.exists()
        assert renamed.name == "ERSC-300-new-name"
        assert renamed.parent == tmp_workspace


# ---------------------------------------------------------------------------
# ensure_epic_link()
# ---------------------------------------------------------------------------

class TestEnsureEpicLink:
    def test_creates_epic_file_and_symlink(self, tmp_workspace: Path):
        ticket_dir = ensure_ticket_dir(tmp_workspace, "ERSC-201", "Sub task")
        epic_file = ensure_epic_link(
            tmp_workspace, ticket_dir, "ERSC-100", "Platform epic",
        )

        # Epic file exists in epics/ dir.
        assert epic_file.exists()
        assert epic_file.parent.name == "epics"
        assert "ERSC-100" in epic_file.name

        # Symlink exists inside orchestrator/ and resolves to the epic file.
        link = ticket_dir / "orchestrator" / "EPIC.md"
        assert link.is_symlink()
        assert link.resolve() == epic_file.resolve()

        # Symlink is relative.
        target = os.readlink(link)
        assert not os.path.isabs(target)

        # Epic file has frontmatter and heading.
        content = epic_file.read_text()
        assert "source: sync" in content
        assert "# ERSC-100: Platform epic" in content

    def test_updates_symlink_when_epic_changes(self, tmp_workspace: Path):
        ticket_dir = ensure_ticket_dir(tmp_workspace, "ERSC-300", "My task")

        # Link to first epic.
        ensure_epic_link(tmp_workspace, ticket_dir, "ERSC-50", "First epic")
        link = ticket_dir / "orchestrator" / "EPIC.md"
        first_target = os.readlink(link)

        # Link to second epic — symlink should update.
        ensure_epic_link(tmp_workspace, ticket_dir, "ERSC-60", "Second epic")
        second_target = os.readlink(link)
        assert first_target != second_target
        assert "ERSC-60" in second_target

    def test_does_not_overwrite_existing_epic_file(self, tmp_workspace: Path):
        ticket_dir = ensure_ticket_dir(tmp_workspace, "ERSC-400", "Task")
        epic_file = ensure_epic_link(
            tmp_workspace, ticket_dir, "ERSC-10", "My epic",
        )
        original_content = epic_file.read_text()

        # Call again — should not overwrite the file.
        ensure_epic_link(tmp_workspace, ticket_dir, "ERSC-10", "My epic")
        assert epic_file.read_text() == original_content


# ---------------------------------------------------------------------------
# orchestrator_dir()
# ---------------------------------------------------------------------------

class TestOrchestratorDir:
    def test_creates_and_returns(self, tmp_workspace: Path):
        ticket = tmp_workspace / "ERSC-400-test"
        ticket.mkdir()
        result = orchestrator_dir(ticket)
        assert result == ticket / "orchestrator"
        assert result.is_dir()


# ---------------------------------------------------------------------------
# enumerate_ticket_dirs()
# ---------------------------------------------------------------------------

class TestEnumerateTicketDirs:
    def test_finds_root_level(self, tmp_workspace: Path):
        d = tmp_workspace / "ERSC-500-task"
        d.mkdir()
        (d / "orchestrator").mkdir()
        results = enumerate_ticket_dirs(tmp_workspace)
        assert ("ERSC-500", d) in results

    def test_skips_epics_dir(self, tmp_workspace: Path):
        """The epics/ directory should not produce results."""
        epics = tmp_workspace / "epics"
        epics.mkdir()
        d = tmp_workspace / "ERSC-500-task"
        d.mkdir()
        (d / "orchestrator").mkdir()
        results = enumerate_ticket_dirs(tmp_workspace)
        assert len(results) == 1
        assert ("ERSC-500", d) in results

    def test_empty_workspace(self, tmp_workspace: Path):
        assert enumerate_ticket_dirs(tmp_workspace) == []

    def test_skips_dotdirs(self, tmp_workspace: Path):
        hidden = tmp_workspace / ".archive"
        hidden.mkdir()
        d = hidden / "ERSC-600-old"
        d.mkdir()
        (d / "orchestrator").mkdir()
        assert enumerate_ticket_dirs(tmp_workspace) == []


# ---------------------------------------------------------------------------
# archive / restore
# ---------------------------------------------------------------------------

class TestArchiveTicket:
    def test_moves_to_archive(self, tmp_workspace: Path):
        d = tmp_workspace / "ERSC-700-task"
        d.mkdir()
        (d / "orchestrator").mkdir()
        result = archive_ticket(tmp_workspace, "ERSC-700")
        assert result is not None
        assert result.parent.name == ".archive"
        assert not d.exists()

    def test_returns_none_when_missing(self, tmp_workspace: Path):
        assert archive_ticket(tmp_workspace, "ERSC-999") is None

    def test_does_not_modify_priority(self, tmp_workspace: Path):
        """archive_ticket no longer touches PRIORITY.md — orchestrator handles that."""
        d = tmp_workspace / "ERSC-700-task"
        d.mkdir()
        (d / "orchestrator").mkdir()
        priority = tmp_workspace / "PRIORITY.md"
        priority.write_text("# Priority\n\n- ERSC-700\n- ERSC-800\n")

        archive_ticket(tmp_workspace, "ERSC-700")

        content = priority.read_text()
        assert "ERSC-700" in content  # still present — orchestrator cleans up
        assert "ERSC-800" in content


class TestRestoreTicket:
    def test_restores_to_root(self, tmp_workspace: Path):
        # Set up archive.
        archive = tmp_workspace / ".archive"
        archive.mkdir()
        d = archive / "ERSC-800-task"
        d.mkdir()
        (d / "orchestrator").mkdir()

        result = restore_ticket(tmp_workspace, "ERSC-800")
        assert result is not None
        assert result.parent == tmp_workspace
        assert result.is_dir()

    def test_returns_none_when_no_archive(self, tmp_workspace: Path):
        assert restore_ticket(tmp_workspace, "ERSC-999") is None


# ---------------------------------------------------------------------------
# workspace.json (load_workspace / save_workspace / ensure_ticket_dir init)
# ---------------------------------------------------------------------------


class TestWorkspaceJson:
    def test_ensure_ticket_dir_creates_workspace_json(self, tmp_workspace: Path):
        ticket_dir = ensure_ticket_dir(tmp_workspace, "ERSC-900", "workspace json test")
        ws_json = ticket_dir / ".duct" / "workspace.json"
        assert ws_json.exists()
        data = json.loads(ws_json.read_text())
        assert data["ticket_key"] == "ERSC-900"
        assert "created_at" in data
        assert data["repos"] == []

    def test_ensure_ticket_dir_workspace_json_idempotent(self, tmp_workspace: Path):
        d = ensure_ticket_dir(tmp_workspace, "ERSC-901", "idempotent test")
        first_created_at = json.loads((d / ".duct" / "workspace.json").read_text())["created_at"]
        ensure_ticket_dir(tmp_workspace, "ERSC-901", "idempotent test")
        second_created_at = json.loads((d / ".duct" / "workspace.json").read_text())["created_at"]
        assert first_created_at == second_created_at

    def test_save_and_load_round_trip(self, tmp_workspace: Path):
        ws_dir = tmp_workspace / "ERSC-910-my-ticket"
        ws_dir.mkdir()
        repo = RepoEntry(
            name="ice-claims",
            origin="git@github.com:org/ice-claims.git",
            branch="feature/ERSC-910-my-ticket",
            base_branch="main",
        )
        ws = Workspace(
            ticket_key="ERSC-910",
            created_at="2025-01-01T00:00:00Z",
            repos=[repo],
            path=str(ws_dir),
        )

        save_workspace(ws)
        loaded = load_workspace(ws_dir)

        assert loaded.ticket_key == "ERSC-910"
        assert loaded.created_at == "2025-01-01T00:00:00Z"
        assert len(loaded.repos) == 1
        r = loaded.repos[0]
        assert r.name == "ice-claims"
        assert r.origin == "git@github.com:org/ice-claims.git"
        assert r.branch == "feature/ERSC-910-my-ticket"
        assert r.base_branch == "main"

    def test_save_does_not_persist_path_field(self, tmp_workspace: Path):
        ws_dir = tmp_workspace / "ERSC-911-ticket"
        ws_dir.mkdir()
        ws = Workspace(ticket_key="ERSC-911", created_at="2025-01-01T00:00:00Z", path=str(ws_dir))
        save_workspace(ws)
        data = json.loads((ws_dir / ".duct" / "workspace.json").read_text())
        assert "path" not in data

    def test_load_missing_raises(self, tmp_workspace: Path):
        ws_dir = tmp_workspace / "ERSC-912-missing"
        ws_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            load_workspace(ws_dir)

    def test_save_no_path_raises(self):
        ws = Workspace(ticket_key="ERSC-913", created_at="2025-01-01T00:00:00Z")
        with pytest.raises(ValueError):
            save_workspace(ws)
