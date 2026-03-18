"""Tests for the tutti priority command."""

from pathlib import Path

from click.testing import CliRunner

from tutti.cli.main import cli


def _init_workspace(runner: CliRunner, root: Path) -> None:
    """Run tutti init to set up config.yaml and PRIORITY.md in the workspace root."""
    runner.invoke(cli, ["--workspace-root", str(root), "init"])


def test_priority_shows_content(tmp_path: Path) -> None:
    """tutti priority should display the contents of PRIORITY.md."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    assert "Priority" in result.output


def test_priority_no_file(tmp_path: Path) -> None:
    """tutti priority should report when PRIORITY.md is missing."""
    runner = CliRunner()
    # Create config.yaml but no PRIORITY.md
    (tmp_path / "config.yaml").write_text("workspace:\n  root: .\n")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    assert "No PRIORITY.md found" in result.output


def test_priority_set(tmp_path: Path) -> None:
    """tutti priority set KEY1 KEY2 should write a new PRIORITY.md."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "set", "PROJ-1", "PROJ-2", "PROJ-3"]
    )

    assert result.exit_code == 0, result.output
    assert "Priority set" in result.output

    content = (tmp_path / "PRIORITY.md").read_text()
    assert "- PROJ-1" in content
    assert "- PROJ-2" in content
    assert "- PROJ-3" in content


def test_priority_set_then_show_roundtrip(tmp_path: Path) -> None:
    """Setting priority then viewing it should show the same keys."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "set", "AAA-1", "BBB-2"]
    )

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    assert "AAA-1" in result.output
    assert "BBB-2" in result.output


def test_priority_set_overwrites(tmp_path: Path) -> None:
    """Running priority set twice should replace the previous list."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "set", "OLD-1"]
    )
    runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "set", "NEW-1", "NEW-2"]
    )

    content = (tmp_path / "PRIORITY.md").read_text()
    assert "OLD-1" not in content
    assert "- NEW-1" in content
    assert "- NEW-2" in content


def test_priority_json_output(tmp_path: Path) -> None:
    """tutti --json priority should produce JSON output."""
    import json

    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--json", "--workspace-root", str(tmp_path), "priority"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert "content" in data


def test_priority_add_appends(tmp_path: Path) -> None:
    """priority add should append a key to the end of the list."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    runner.invoke(cli, ["--workspace-root", str(tmp_path), "priority", "set", "AAA-1"])
    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "add", "BBB-2"]
    )

    assert result.exit_code == 0, result.output
    content = (tmp_path / "PRIORITY.md").read_text()
    assert "- AAA-1" in content
    assert "- BBB-2" in content
    # BBB-2 should come after AAA-1
    assert content.index("AAA-1") < content.index("BBB-2")


def test_priority_remove_existing(tmp_path: Path) -> None:
    """priority remove should remove a key from the list."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "set", "AAA-1", "BBB-2"]
    )
    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "remove", "AAA-1"]
    )

    assert result.exit_code == 0, result.output
    content = (tmp_path / "PRIORITY.md").read_text()
    assert "AAA-1" not in content
    assert "- BBB-2" in content


def test_priority_remove_missing(tmp_path: Path) -> None:
    """priority remove for a key not in the list should warn."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "priority", "remove", "ZZZ-99"]
    )

    assert result.exit_code == 0, result.output
    assert "not in" in result.output.lower()
