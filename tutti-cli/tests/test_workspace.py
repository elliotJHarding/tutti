"""Tests for tutti.workspace utilities."""

from pathlib import Path

from tutti.workspace import (
    archive_ticket,
    ensure_ticket_dir,
    enumerate_ticket_dirs,
    orchestrator_dir,
    resolve_ticket_dir,
    restore_ticket,
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

    def test_finds_under_epic(self, tmp_workspace: Path):
        epic = tmp_workspace / "ERSC-50-big-epic"
        epic.mkdir()
        d = epic / "ERSC-100-some-task"
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

    def test_creates_under_epic(self, tmp_workspace: Path):
        path = ensure_ticket_dir(
            tmp_workspace, "ERSC-201", "Sub task",
            epic_key="ERSC-100", epic_summary="Platform epic",
        )
        assert "ERSC-100-platform-epic" in str(path.parent.name)
        assert (path / "orchestrator").is_dir()

    def test_moves_when_epic_changes(self, tmp_workspace: Path):
        # Start at root level.
        original = ensure_ticket_dir(tmp_workspace, "ERSC-300", "My task")
        assert original.parent == tmp_workspace

        # Now assign an epic — should move.
        moved = ensure_ticket_dir(
            tmp_workspace, "ERSC-300", "My task",
            epic_key="ERSC-50", epic_summary="Epic",
        )
        assert not original.exists()
        assert moved.exists()
        assert moved.parent.name.startswith("ERSC-50-")


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

    def test_finds_under_epic(self, tmp_workspace: Path):
        epic = tmp_workspace / "ERSC-10-epic"
        epic.mkdir()
        d = epic / "ERSC-501-sub"
        d.mkdir()
        (d / "orchestrator").mkdir()
        results = enumerate_ticket_dirs(tmp_workspace)
        assert ("ERSC-501", d) in results
        # Epic itself should not appear as a ticket.
        keys = [k for k, _ in results]
        assert "ERSC-10" not in keys

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

    def test_restores_under_epic(self, tmp_workspace: Path):
        # Create epic dir.
        epic = tmp_workspace / "ERSC-50-epic"
        epic.mkdir()
        # Set up archive.
        archive = tmp_workspace / ".archive"
        archive.mkdir()
        d = archive / "ERSC-801-task"
        d.mkdir()
        (d / "orchestrator").mkdir()

        result = restore_ticket(tmp_workspace, "ERSC-801", epic_key="ERSC-50")
        assert result is not None
        assert result.parent == epic

    def test_returns_none_when_no_archive(self, tmp_workspace: Path):
        assert restore_ticket(tmp_workspace, "ERSC-999") is None
