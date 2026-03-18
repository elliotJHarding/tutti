"""Tests for the tutti workspace command."""

import json
from pathlib import Path

from click.testing import CliRunner

from tutti.cli.main import cli


def _init_workspace(runner: CliRunner, root: Path) -> None:
    """Run tutti init to set up config.yaml in the workspace root."""
    runner.invoke(cli, ["--workspace-root", str(root), "init"])


def _create_ticket_dir(root: Path, key: str, slug: str = "") -> Path:
    """Manually create a ticket directory with orchestrator subdir.

    This replaces the removed ``workspace create`` command.
    """
    dirname = f"{key}-{slug}" if slug else f"{key}-{key.lower()}"
    ticket_dir = root / dirname
    (ticket_dir / "orchestrator").mkdir(parents=True)
    return ticket_dir


def test_workspace_status_empty(tmp_path: Path) -> None:
    """workspace status with no tickets should report nothing found."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "No tickets found" in result.output


def test_workspace_status_shows_tickets(tmp_path: Path) -> None:
    """workspace status should list tickets found in the workspace."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-10")
    _create_ticket_dir(tmp_path, "PROJ-20")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "PROJ-10" in result.output
    assert "PROJ-20" in result.output


def test_workspace_status_json(tmp_path: Path) -> None:
    """workspace status --json should produce parseable JSON output."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-50")

    result = runner.invoke(
        cli, ["--json", "--workspace-root", str(tmp_path), "workspace", "status"]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["key"] == "PROJ-50"


def test_workspace_path_found(tmp_path: Path) -> None:
    """workspace path KEY should print the ticket directory path."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "PROJ-99", "some-feature")

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "path", "PROJ-99"]
    )

    assert result.exit_code == 0, result.output
    assert str(ticket_dir) in result.output.strip()


def test_workspace_path_not_found(tmp_path: Path) -> None:
    """workspace path KEY should fail when no matching directory exists."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "path", "NOPE-1"]
    )

    assert result.exit_code != 0
