"""Tests for tutti orchestrate command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tutti.cli.main import cli
from tutti.config import TrustConfig, WorkspaceConfig, save_config


def _init_workspace(root: Path) -> None:
    cfg = WorkspaceConfig(root=root)
    save_config(cfg, root)


class TestOrchestrate:
    def test_dry_run_shows_command(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert result.exit_code == 0
        assert "/usr/local/bin/claude" in result.output
        assert "--add-dir" in result.output

    def test_dry_run_with_ticket(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                [
                    "--workspace-root", str(tmp_path),
                    "orchestrate", "--ticket", "ERSC-1278", "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "ERSC-1278" in result.output

    def test_missing_claude_binary(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value=None):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate"],
            )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_allowed_tools_default(self, tmp_path: Path) -> None:
        """Default trust config includes Bash (git_commit=propose)."""
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert "Bash" in result.output

    def test_allowed_tools_deny_all(self, tmp_path: Path) -> None:
        """When all shell actions are deny, Bash is excluded."""
        cfg = WorkspaceConfig(
            root=tmp_path,
            trust=TrustConfig(
                git_commit="deny",
                git_push="deny",
                pr_create="deny",
                pr_merge="deny",
            ),
        )
        save_config(cfg, tmp_path)

        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert "Bash" not in result.output
        assert "Read" in result.output

    def test_json_dry_run(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                [
                    "--json",
                    "--workspace-root", str(tmp_path),
                    "orchestrate", "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert '"command"' in result.output
