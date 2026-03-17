"""Tests for the tutti workspace command."""

from pathlib import Path

from click.testing import CliRunner

from tutti.cli.main import cli


def _init_workspace(runner: CliRunner, root: Path) -> None:
    """Run tutti init to set up config.yaml in the workspace root."""
    runner.invoke(cli, ["--workspace-root", str(root), "init"])


def test_workspace_create_creates_directory(tmp_path: Path) -> None:
    """workspace create KEY should create a ticket directory with orchestrator subdir."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "create", "PROJ-100"],
    )

    assert result.exit_code == 0, result.output
    assert "Workspace created" in result.output

    # Should have created a directory starting with PROJ-100-
    dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d.name.startswith("PROJ-100-")]
    assert len(dirs) == 1
    assert (dirs[0] / "orchestrator").is_dir()


def test_workspace_create_with_summary(tmp_path: Path) -> None:
    """workspace create KEY --summary 'foo bar' should include slug in dir name."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "workspace", "create",
         "PROJ-200", "--summary", "Fix login bug"],
    )

    assert result.exit_code == 0, result.output

    dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d.name.startswith("PROJ-200-")]
    assert len(dirs) == 1
    assert "fix-login-bug" in dirs[0].name


def test_workspace_create_with_epic(tmp_path: Path) -> None:
    """workspace create KEY --epic EPIC-1 should nest under epic directory."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli,
        [
            "--workspace-root", str(tmp_path),
            "workspace", "create", "PROJ-300",
            "--epic", "EPIC-1",
            "--epic-summary", "Authentication Epic",
        ],
    )

    assert result.exit_code == 0, result.output

    # Should be nested: root / EPIC-1-authentication-epic / PROJ-300-proj-300 / orchestrator
    epic_dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d.name.startswith("EPIC-1-")]
    assert len(epic_dirs) == 1
    ticket_dirs = [
        d for d in epic_dirs[0].iterdir()
        if d.is_dir() and d.name.startswith("PROJ-300-")
    ]
    assert len(ticket_dirs) == 1
    assert (ticket_dirs[0] / "orchestrator").is_dir()


def test_workspace_status_empty(tmp_path: Path) -> None:
    """workspace status with no tickets should report nothing found."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "No tickets found" in result.output


def test_workspace_status_shows_tickets(tmp_path: Path) -> None:
    """workspace status should list created tickets."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    # Create two tickets
    runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "create", "PROJ-10"])
    runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "create", "PROJ-20"])

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "PROJ-10" in result.output
    assert "PROJ-20" in result.output


def test_workspace_status_json(tmp_path: Path) -> None:
    """workspace status --json should produce parseable JSON output."""
    import json

    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "create", "PROJ-50"])

    result = runner.invoke(
        cli, ["--json", "--workspace-root", str(tmp_path), "workspace", "status"]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["key"] == "PROJ-50"
