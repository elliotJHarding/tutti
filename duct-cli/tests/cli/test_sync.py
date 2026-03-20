"""Tests for the duct sync command."""

from pathlib import Path

from click.testing import CliRunner

from duct.cli.main import cli


def test_sync_help_shows_subcommands() -> None:
    """duct sync --help should list all subcommands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--help"])

    assert result.exit_code == 0, result.output
    assert "jira" in result.output
    assert "github" in result.output
    assert "ci" in result.output
    assert "sessions" in result.output
    assert "workspace" in result.output


def test_sync_jira_without_auth_shows_error(tmp_path: Path) -> None:
    """duct sync jira without JIRA_EMAIL/JIRA_TOKEN should report an auth error."""
    import os

    runner = CliRunner()
    env = {k: v for k, v in os.environ.items() if k not in ("JIRA_EMAIL", "JIRA_TOKEN")}
    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "sync", "jira"],
        env=env,
    )

    assert result.exit_code != 0


def test_sync_subcommands_are_registered() -> None:
    """All expected subcommands should be registered on the sync group."""
    runner = CliRunner()
    expected = ["jira", "github", "ci", "sessions", "workspace"]

    for subcmd in expected:
        result = runner.invoke(cli, ["sync", subcmd, "--help"])
        assert result.exit_code == 0, f"Subcommand '{subcmd}' failed: {result.output}"


def test_sync_without_subcommand_exits_nonzero_when_sources_skipped(tmp_path: Path) -> None:
    """duct sync with no auth configured should warn about skipped sources and exit non-zero."""
    import os

    config_path = tmp_path / "config.yaml"
    config_path.write_text("workspace:\n  root: .\n")

    runner = CliRunner()
    env = {k: v for k, v in os.environ.items()
           if k not in ("JIRA_EMAIL", "JIRA_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")}
    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "sync"],
        env=env,
    )

    assert result.exit_code != 0, result.output
    assert "skipped" in result.output


def test_sync_skipped_sources_show_warnings(tmp_path: Path) -> None:
    """Skipped sources should produce warning messages with the reason."""
    import os

    config_path = tmp_path / "config.yaml"
    config_path.write_text("workspace:\n  root: .\n")

    runner = CliRunner()
    env = {k: v for k, v in os.environ.items()
           if k not in ("JIRA_EMAIL", "JIRA_TOKEN")}
    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "sync"],
        env=env,
    )

    assert "jira: skipped" in result.output


def test_sync_force_flag() -> None:
    """The --force flag should be accepted without error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--force", "--help"])
    assert result.exit_code == 0, result.output
    assert "--force" in result.output
