"""Tests for the duct priority command."""

from pathlib import Path

from click.testing import CliRunner

from duct.cli.main import cli


def _init_workspace(runner: CliRunner, root: Path) -> None:
    """Run duct init to set up config.yaml and PRIORITY.md in the workspace root."""
    runner.invoke(cli, ["--workspace-root", str(root), "init"])


def test_priority_shows_content(tmp_path: Path) -> None:
    """duct priority should display the contents of PRIORITY.md."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    assert "Priority" in result.output


def test_priority_no_file(tmp_path: Path) -> None:
    """duct priority should report when PRIORITY.md is missing."""
    runner = CliRunner()
    # Create config.yaml but no PRIORITY.md
    (tmp_path / "config.yaml").write_text("workspace:\n  root: .\n")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    assert "No PRIORITY.md found" in result.output


def test_priority_json_output(tmp_path: Path) -> None:
    """duct --json priority should produce JSON output."""
    import json

    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--json", "--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert "content" in data


def test_priority_add_appends(tmp_path: Path) -> None:
    """priority add should append a key to the end of the file."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "add", "BBB-2"]
    )

    assert result.exit_code == 0, result.output
    content = (tmp_path / "PRIORITY.md").read_text()
    assert "- BBB-2" in content


def test_priority_add_with_note(tmp_path: Path) -> None:
    """priority add KEY NOTE should append '- KEY — note' to the file."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "priority", "add", "ERSC-1278", "PR", "open,", "awaiting", "review"],
    )

    assert result.exit_code == 0, result.output
    content = (tmp_path / "PRIORITY.md").read_text()
    assert "- ERSC-1278 — PR open, awaiting review" in content


def test_priority_add_preserves_existing(tmp_path: Path) -> None:
    """priority add should not destroy existing rich content."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    rich_content = (
        "# Priority\n\n"
        "## Current Focus\n\n"
        "- **AAA-1** — important work\n"
    )
    (tmp_path / "PRIORITY.md").write_text(rich_content)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "add", "BBB-2"]
    )

    assert result.exit_code == 0, result.output
    content = (tmp_path / "PRIORITY.md").read_text()
    # Original content preserved
    assert "## Current Focus" in content
    assert "**AAA-1** — important work" in content
    # New entry appended
    assert "- BBB-2" in content


def test_priority_add_warns_duplicate(tmp_path: Path) -> None:
    """priority add should warn when the key already exists in the file."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)
    (tmp_path / "PRIORITY.md").write_text("# Priority\n\n- AAA-1\n")

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "add", "AAA-1"]
    )

    assert result.exit_code == 0, result.output
    assert "already in" in result.output.lower()
