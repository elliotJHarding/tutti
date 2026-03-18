"""Tests for the tutti archive command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tutti.cli.main import cli


def _init_workspace(root: Path) -> None:
    """Write a minimal config.yaml so find_workspace_root succeeds."""
    (root / "config.yaml").write_text("workspace:\n  root: .\n")


def _make_archived_ticket(root: Path, key: str, slug: str) -> Path:
    """Create a ticket directory inside .archive/ with an orchestrator/ subdir."""
    archive = root / ".archive"
    d = archive / f"{key}-{slug}"
    orch = d / "orchestrator"
    orch.mkdir(parents=True)
    return d


class TestArchiveList:
    def test_empty_archive(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "archive"])

        assert result.exit_code == 0, result.output
        assert "No archived tickets" in result.output

    def test_no_archive_dir(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "archive", "list"])

        assert result.exit_code == 0, result.output
        assert "No archived tickets" in result.output

    def test_with_archived_tickets(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        _make_archived_ticket(tmp_path, "ERSC-100", "old-task")
        _make_archived_ticket(tmp_path, "ERSC-200", "another-task")

        runner = CliRunner()
        result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "archive", "list"])

        assert result.exit_code == 0, result.output
        assert "ERSC-100" in result.output
        assert "ERSC-200" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        _make_archived_ticket(tmp_path, "ERSC-100", "old-task")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "--workspace-root", str(tmp_path), "archive", "list"]
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["key"] == "ERSC-100"

    def test_invoke_without_subcommand(self, tmp_path: Path) -> None:
        """Running `tutti archive` with no subcommand should behave like `archive list`."""
        _init_workspace(tmp_path)
        _make_archived_ticket(tmp_path, "ERSC-300", "some-task")

        runner = CliRunner()
        result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "archive"])

        assert result.exit_code == 0, result.output
        assert "ERSC-300" in result.output


class TestArchiveAdd:
    def test_add_existing_ticket(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        # Create a ticket directory in the workspace
        ticket_dir = tmp_path / "ERSC-100-some-task"
        (ticket_dir / "orchestrator").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--workspace-root", str(tmp_path), "archive", "add", "ERSC-100"]
        )

        assert result.exit_code == 0, result.output
        assert "Archived" in result.output
        assert (tmp_path / ".archive" / "ERSC-100-some-task").is_dir()
        assert not ticket_dir.exists()

    def test_add_missing_ticket(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--workspace-root", str(tmp_path), "archive", "add", "ERSC-999"]
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestArchiveRestore:
    def test_restore_existing(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        _make_archived_ticket(tmp_path, "ERSC-100", "old-task")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--workspace-root", str(tmp_path), "archive", "restore", "ERSC-100"]
        )

        assert result.exit_code == 0, result.output
        assert "Restored" in result.output
        # Ticket should now be in workspace root, not archive.
        assert (tmp_path / "ERSC-100-old-task").is_dir()
        assert not (tmp_path / ".archive" / "ERSC-100-old-task").exists()

    def test_restore_missing(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--workspace-root", str(tmp_path), "archive", "restore", "ERSC-999"]
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_restore_under_epic(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        # Create an epic directory.
        epic = tmp_path / "ERSC-50-big-epic"
        epic.mkdir()
        _make_archived_ticket(tmp_path, "ERSC-100", "old-task")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path),
             "archive", "restore", "ERSC-100", "--epic", "ERSC-50"],
        )

        assert result.exit_code == 0, result.output
        assert "Restored" in result.output
        assert (epic / "ERSC-100-old-task").is_dir()
